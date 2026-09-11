#!/usr/bin/env python
"""CGR Cotizador — Web application launcher.

Usage:
    python run_web.py              # default: localhost:8000
    python run_web.py --port 3000  # custom port
    python run_web.py --reload     # auto-reload on file changes (dev)
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="CGR Cotizador · Web App")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Port")
    parser.add_argument("--reload", action="store_true", help="Auto-reload (dev)")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn not installed.  Run: pip install uvicorn[standard]")
        sys.exit(1)

    print(f"""
    ╔══════════════════════════════════════════╗
    ║  CGR Cotizador · LEAN AI-LAB             ║
    ║  Pahua . RFQ Quoter                  ║
    ║                                          ║
    ║  → http://{args.host}:{args.port}        ║
    ╚══════════════════════════════════════════╝
    """)

    uvicorn.run(
        "api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
