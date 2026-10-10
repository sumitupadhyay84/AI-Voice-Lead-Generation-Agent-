"""
LeadPulse.ai Calling Platform — Server Launcher
Run: python server.py
"""
import os
import sys

# Add parent dir to path so .env is loaded from workspace root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure stdout handles utf-8 if needed on Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from api.app import app, init_db

if __name__ == '__main__':
    init_db()
    print("\n" + "=" * 50)
    print("  LeadPulse.ai Calling Platform")
    print("=" * 50)
    print("  Web UI  : http://localhost:5000")
    print("  API     : http://localhost:5000/api")
    print("  Login   : admin@leadpulse.ai / admin123")
    print("=" * 50 + "\n")
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
