from flask import Blueprint, render_template, redirect, url_for, session, request
from . import auth, dashboard

dashboard_bp = Blueprint('dashboard', __name__, template_folder='templates', static_folder='static')

# Import auth routes
dashboard_bp.add_url_rule('/login', view_func=auth.login)
dashboard_bp.add_url_rule('/callback', view_func=auth.callback)
dashboard_bp.add_url_rule('/logout', view_func=auth.logout)

# Import dashboard routes
dashboard_bp.add_url_rule('/', view_func=dashboard.index)
dashboard_bp.add_url_rule('/settings', view_func=dashboard.settings, methods=['GET', 'POST'])
dashboard_bp.add_url_rule('/analytics', view_func=dashboard.analytics)

def init_app(app):
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
