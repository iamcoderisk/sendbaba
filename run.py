"""
SendBaba Application Entry Point
"""
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Development only - use Gunicorn in production
    app.run(host='0.0.0.0', port=5001, debug=False)
