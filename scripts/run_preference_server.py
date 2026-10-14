"""Local collection API and Preference Agent worker; --collection-only disables paid calls."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
import argparse
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer
from wsgiref.simple_server import WSGIRequestHandler
from wsgiref.simple_server import make_server

from fashion_recommendation_v2.server.preference_http import PreferenceAPI
from fashion_recommendation_v2.server.preference_runtime import PreferenceRuntime
from fashion_recommendation_v2.server.preference_service import PreferenceService


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True

    def get_request(self):
        socket, address = super().get_request()
        socket.settimeout(10)
        return socket, address


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *_):
        pass  # Do not emit cookie/IP/request payload into shared access logs.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', default='usage/preference.sqlite3')
    parser.add_argument('--artifact-root', default='usage/preference_artifacts')
    parser.add_argument('--origin', action='append', help='Allowed frontend origin; repeat as needed')
    parser.add_argument('--secure-cookie', action='store_true', help='Enable for HTTPS deployments')
    parser.add_argument('--model', default='gpt-5.6-sol')
    parser.add_argument('--preference-version', choices=['v0','v1','v2','v3','v4'], default='v4')
    parser.add_argument('--collection-only', action='store_true', help='Collect events without LLM updates')
    parser.add_argument('--recommendations', action='store_true', help='Enable Orchestrator recommendation and confirmation API')
    args = parser.parse_args()
    if args.recommendations and args.collection_only:
        parser.error('--recommendations cannot be combined with --collection-only')
    if args.recommendations and args.preference_version != 'v4':
        parser.error('Current recommendation consumers require Preference v4; use --preference-version v4')
    service = PreferenceService(args.db, artifact_root=args.artifact_root)
    processor = None
    if not args.collection_only:
        from pathlib import Path
        from dotenv import load_dotenv
        from fashion_recommendation_v2.llm.openai_adapter import OpenAIStructuredLLM
        from fashion_recommendation_v2.agents.preference import PreferenceAgent
        load_dotenv(Path(__file__).resolve().parents[1] / '.env')
        processor = PreferenceAgent(OpenAIStructuredLLM(model=args.model), service, version=args.preference_version)
    runtime = PreferenceRuntime(service, processor=processor)
    recommendations = None
    if args.recommendations:
        from fashion_recommendation_v2.server.recommendation_factory import build_recommendation_service
        from fashion_recommendation_v2.server.recommendation_runtime import RecommendationRuntime
        recommendations = RecommendationRuntime(build_recommendation_service(service, model=args.model))
    app = PreferenceAPI(service, allowed_origins=args.origin or [f'http://{args.host}:{args.port}'],
                        secure_cookie=args.secure_cookie, runtime=runtime, recommendations=recommendations)
    with make_server(args.host, args.port, app, server_class=ThreadedServer, handler_class=QuietHandler) as server:
        try:
            if recommendations:
                recommendations.start()
            runtime.start()
            print(f'Preference collection API: http://{args.host}:{args.port}', flush=True)
            print('Preference Agent enabled.' if processor else 'Collection only: pending jobs preserved.', flush=True)
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            runtime.stop()
            if recommendations:
                recommendations.stop()


if __name__ == '__main__':
    main()
