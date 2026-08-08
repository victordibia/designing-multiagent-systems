"""
CLI interface for PicoAgents WebUI.

Provides command-line entry point for launching the web interface to interact
with PicoAgents entities (agents, orchestrators, workflows).
"""

import argparse
import logging
import sys
import webbrowser
from pathlib import Path
from typing import Any, Optional

import uvicorn

from ._discovery import PicoAgentsScanner
from ._server import create_app

logger: logging.Logger = logging.getLogger(__name__)


def webui(
    entities_dir: Optional[str] = None,
    port: int = 8080,
    host: str = "127.0.0.1",
    auto_open: bool = True,
    reload: bool = False,
    log_level: str = "info",
    app: Optional[Any] = None,
) -> None:
    """Launch PicoAgents WebUI server.

    Args:
        entities_dir: Directory to scan for PicoAgents entities.
                      If None, only serves entities registered programmatically.
                      CLI usage defaults to current directory.
        port: Port to run the server on
        host: Host to bind the server to
        auto_open: Whether to automatically open browser
        reload: Enable auto-reload for development
        log_level: Logging level (debug, info, warning, error)
        app: Optional pre-configured FastAPI app (for programmatic use)
    """
    # Only perform discovery if entities_dir is provided and no app given
    if entities_dir is not None and app is None:
        # Convert to absolute path
        entities_path = Path(entities_dir).resolve()

        if not entities_path.exists():
            print(f"❌ Directory does not exist: {entities_path}")
            sys.exit(1)

        if not entities_path.is_dir():
            print(f"❌ Path is not a directory: {entities_path}")
            sys.exit(1)

        print(f"🔍 Scanning {entities_path} for agents, orchestrators, and workflows...")

        # Quick discovery check to provide feedback
        scanner = PicoAgentsScanner(str(entities_path))
        try:
            discovered = scanner.discover_entities()

            if discovered:
                print(f"📋 Found {len(discovered)}:")
                for entity in discovered:
                    print(f"   • {entity.id} ({entity.type})")
            else:
                print(f"⚠️  No agents, orchestrators, or workflows found in {entities_path}")
                print("   Make sure the directory contains valid Python modules with:")
                print("   - agent = Agent(...)")
                print("   - orchestrator = RoundRobinOrchestrator(...)")
                print("   - workflow = Workflow(...)")
        except Exception as e:
            print(f"⚠️  Error during discovery: {e}")
            print("   Continuing anyway - may be discovered at runtime")

    print(f"🚀 Starting PicoAgents WebUI on http://{host}:{port}")

    # Create FastAPI app if not provided
    if app is None:
        app = create_app(entities_dir=entities_dir)

    if auto_open:
        # Open browser after short delay
        def open_browser() -> None:
            import threading
            import time

            def _open() -> None:
                time.sleep(1.5)  # Give server time to start
                webbrowser.open(f"http://{host}:{port}")

            threading.Thread(target=_open, daemon=True).start()

        open_browser()

    # Start server
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
        access_log=True,  # Always show access logs for better debugging
    )


def main() -> None:
    """CLI entry point for picoagentsui command."""
    parser = argparse.ArgumentParser(
        description="Launch PicoAgents WebUI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  picoagentsui                    # Scan current directory
  picoagentsui --dir ./agents     # Scan specific directory
  picoagentsui --port 8000        # Use different port
  picoagentsui --no-open          # Don't open browser
  picoagentsui --reload           # Enable auto-reload for development
        """,
    )

    parser.add_argument(
        "--dir",
        default=".",
        help="Directory to scan for agents, orchestrators, and workflows (default: current directory)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8080,
        help="Port to run server on (default: 8080)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind server to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't automatically open browser",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Logging level (default: info)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        webui(
            entities_dir=args.dir,
            port=args.port,
            host=args.host,
            auto_open=not args.no_open,
            reload=args.reload,
            log_level=args.log_level,
        )
    except KeyboardInterrupt:
        print("\n👋 Shutting down PicoAgents WebUI")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error starting WebUI: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
