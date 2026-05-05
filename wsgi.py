"""
Production WSGI Entry Point
Used by Gunicorn and other WSGI servers
"""

import os
from app import app as application

if __name__ == "__main__":
    application.run()

# Determine environment
env = os.getenv('FLASK_ENV', 'production')

# Create app
app = create_app(env)

# Shell context for Flask CLI
@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'User': app.import_name + '.models.user.User',
        'Fuel': app.import_name + '.models.fuel.Fuel',
        'Sale': app.import_name + '.models.sale.Sale',
    }

if __name__ == '__main__':
    app.run()
