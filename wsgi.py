"""
WSGI Entry Point for SendBaba
"""
import sys
sys.path.insert(0, '/opt/sendbaba-staging')

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run()
