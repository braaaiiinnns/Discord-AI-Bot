import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, callback, Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import json
import logging
import time
import threading
import sqlite3
import os
import secrets
from flask import Flask, session, redirect, url_for, request, flash
from flask_session import Session
from datetime import datetime, timedelta
from pathlib import Path
from flask_login import current_user, login_required
from .auth import DiscordAuthManager, DashboardUser

logger = logging.getLogger('discord_bot.dashboard')

class Dashboard:
    """
    Dashboard for visualizing discord bot data with optimized O(log n) access complexity.
    Uses caching, SQL indexes, and Discord SSO authentication for security.
    """
    
    def __init__(self, message_monitor, host="127.0.0.1", port=8050, debug=False, 
                 require_auth=True, secret_key=None):
        """
        Initialize the dashboard with a reference to the message monitor.
        
        Args:
            message_monitor (MessageMonitor): The message monitor instance
            host (str): Host to run the dashboard on
            port (int): Port to run the dashboard on
            debug (bool): Whether to run in debug mode
            require_auth (bool): Whether to require Discord authentication
            secret_key (str): Secret key for Flask session (auto-generated if None)
        """
        self.message_monitor = message_monitor
        self.host = host
        self.port = port
        self.debug = debug
        self.require_auth = require_auth
        self.secret_key = secret_key or secrets.token_hex(32)
        
        # Initialize Flask server with session support
        self.server = Flask(__name__)
        self.server.config.update(
            SECRET_KEY=self.secret_key,
            SESSION_TYPE='filesystem',
            SESSION_FILE_DIR=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'flask_session'),
            PERMANENT_SESSION_LIFETIME=timedelta(days=7),
            SESSION_PERMANENT=True,
            SESSION_USE_SIGNER=True,  # Add signature for security
            SESSION_COOKIE_SECURE=False,  # Set to True in production with HTTPS
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE='Lax'  # Helps with CSRF protection
        )
        
        # Ensure session directory exists
        os.makedirs(self.server.config['SESSION_FILE_DIR'], exist_ok=True)
        
        # Initialize session with updated pattern
        Session(self.server)
        
        # Initialize Dash app with updated syntax
        self.app = dash.Dash(
            __name__,
            server=self.server,
            external_stylesheets=[dbc.themes.DARKLY],
            suppress_callback_exceptions=True,
            url_base_pathname='/',
            use_pages=False  # Not using dash.page module yet
        )
        
        # Initialize Discord authentication
        if self.require_auth:
            self.auth_manager = DiscordAuthManager(
                self.server,
                bot_client=self.message_monitor.client if hasattr(self.message_monitor, 'client') else None
            )
            # Register auth blueprint
            self.server.register_blueprint(self.auth_manager.bp, url_prefix='/')
        
        self.thread = None
        self.running = False
        
        # Setup cache with better structure
        self.cache = {
            'last_update': 0,
            'dashboard_data': {},  # Guild-specific
            'update_interval': 60  # seconds
        }
        
        # Configure the dashboard layout and callbacks
        self._setup_layout()
        self._setup_callbacks()
        
        # Authentication middleware
        self._setup_auth_middleware()
        
        # Add a basic index route to the Flask server
        @self.server.route('/')
        def index():
            return 'Dashboard Home Page'
        
        logger.info("Dashboard initialized with Discord SSO authentication")
    
    def _setup_auth_middleware(self):
        """Set up authentication middleware for protected routes"""
        if not self.require_auth:
            return
            
        # Add login check with updated patterns
        @self.server.before_request
        def check_login():
            # Skip authentication for auth routes and static files
            exempt_routes = ['/login', '/callback', '/logout', '/favicon.ico']
            if request.path in exempt_routes or request.path.startswith('/assets/'):
                return None
                
            # Redirect to login if not authenticated
            if not current_user.is_authenticated:
                if request.path != '/':
                    return redirect(url_for('auth.login', next=request.url))
                return redirect(url_for('auth.login'))
                
            return None
    
    def _setup_layout(self):
        """Configure the dashboard layout with tabs for different data views."""
        # Create sidebar with updated Bootstrap 5 classes
        sidebar = html.Div(
            [
                html.H2("Discord Bot", className="display-6 text-center"),
                html.Hr(),
                html.Div([
                    html.Img(id="user-avatar", className="rounded-circle mx-auto d-block mb-2", width=64, height=64),
                    html.H5(id="user-name", className="text-center mb-3")
                ], id="user-info", className="mb-2"),
                html.Div([
                    dbc.Select(id="guild-selector", className="mb-3")
                ], id="guild-dropdown"),
                html.P("Data Dashboard", className="lead text-center"),
                dbc.Nav(
                    [
                        dbc.NavLink("Overview", href="/", active="exact"),
                        dbc.NavLink("Message Activity", href="/messages", active="exact"),
                        dbc.NavLink("User Engagement", href="/users", active="exact"),
                        dbc.NavLink("Files & Media", href="/files", active="exact"),
                        dbc.NavLink("AI Interactions", href="/ai", active="exact"),
                    ],
                    vertical=True,
                    pills=True,
                ),
                html.Hr(),
                html.Div(id="last-update-time", className="text-center text-muted small"),
                html.Div([
                    dbc.Button("Refresh Data", id="refresh-button", color="primary", className="mt-2 mb-3")
                ], className="text-center"),
                html.Div([
                    dbc.Button("Log Out", id="logout-button", color="danger", className="mt-2", href="/logout")
                ], className="text-center") if self.require_auth else html.Div()
            ],
            className="bg-dark text-white p-4",
            style={"width": "250px", "position": "fixed", "height": "100vh", "overflowY": "auto"}
        )
        
        # Main content area
        content = html.Div(
            id="page-content",
            className="p-4",
            style={"margin-left": "250px"}
        )
        
        # Full layout with sidebar and content area
        self.app.layout = html.Div([
            dcc.Location(id="url"),
            dcc.Store(id="dashboard-data"),
            dcc.Store(id="selected-guild-id", data=None),
            dcc.Interval(id="interval-component", interval=60000, n_intervals=0),  # Update every minute
            sidebar,
            content
        ])
    
    def _setup_callbacks(self):
        """Set up all the Dash callbacks for the dashboard using updated callback pattern."""
        
        @callback(
            [Output("user-avatar", "src"),
             Output("user-name", "children"),
             Output("guild-selector", "options"),
             Output("selected-guild-id", "data")],
            [Input("url", "pathname")],
            prevent_initial_call=False,
        )
        def update_user_info(pathname):
            """Update user info and guild selector"""
            if not self.require_auth or not current_user.is_authenticated:
                return (
                    "https://cdn.discordapp.com/embed/avatars/0.png",
                    "Guest User",
                    [{"label": "Demo Guild", "value": "demo"}],
                    "demo"
                )
            
            # Get user's guilds where the bot is also present
            bot_guild_ids = []
            if hasattr(self.message_monitor, 'client') and hasattr(self.message_monitor.client, 'guilds'):
                bot_guild_ids = [str(g.id) for g in self.message_monitor.client.guilds]
            
            # Filter user's guilds to only include ones where the bot is also present
            shared_guilds = []
            for guild in current_user.guilds:
                if str(guild.get('id')) in bot_guild_ids:
                    shared_guilds.append({
                        "label": guild.get('name', 'Unknown Guild'),
                        "value": guild.get('id')
                    })
            
            # Default to first guild if none selected
            selected_guild = shared_guilds[0]['value'] if shared_guilds else "demo"
            
            return (
                current_user.get_avatar_url(),
                current_user.get_display_name(),
                shared_guilds or [{"label": "Demo Guild", "value": "demo"}],
                selected_guild
            )
        
        @callback(
            Output("selected-guild-id", "data"),
            [Input("guild-selector", "value")],
            prevent_initial_call=True
        )
        def update_selected_guild(selected_guild):
            """Update the selected guild when changed in dropdown"""
            # Invalidate cache for the new guild
            self._invalidate_cache_for_guild(selected_guild)
            return selected_guild
        
        @callback(
            Output("dashboard-data", "data"),
            [Input("interval-component", "n_intervals"),
             Input("refresh-button", "n_clicks"),
             Input("selected-guild-id", "data")],
            prevent_initial_call=False
        )
        async def update_data(n_intervals, n_clicks, guild_id):
            """Fetch and update dashboard data at regular intervals or on manual refresh."""
            if not guild_id:
                return {"error": "No guild selected"}
                
            try:
                current_time = time.time()
                guild_cache = self.cache['dashboard_data'].get(guild_id, {
                    'data': None,
                    'timestamp': 0
                })
                
                # Check if we need to update data (cache expired or forced refresh)
                if (not guild_cache.get('data') or 
                    current_time - guild_cache.get('timestamp', 0) > self.cache['update_interval']):
                    
                    # Get data from message monitor with guild filter
                    filter_criteria = None
                    if guild_id != "demo":
                        filter_criteria = {"guild_id": guild_id}
                        
                    dashboard_data = await self.message_monitor.get_dashboard_data(filter_criteria)
                    
                    # Update cache
                    if guild_id not in self.cache['dashboard_data']:
                        self.cache['dashboard_data'][guild_id] = {}
                        
                    self.cache['dashboard_data'][guild_id]['data'] = dashboard_data
                    self.cache['dashboard_data'][guild_id]['timestamp'] = current_time
                    
                    logger.info(f"Dashboard data refreshed for guild {guild_id}")
                    return dashboard_data
                
                # Return cached data
                return guild_cache['data']
            except Exception as e:
                logger.error(f"Error updating dashboard data: {e}", exc_info=True)
                return {"error": str(e)}
        
        @callback(
            Output("last-update-time", "children"),
            [Input("dashboard-data", "data")]
        )
        def update_last_update_time(data):
            """Update the last update time display."""
            if data and not isinstance(data, dict) or (isinstance(data, dict) and 'error' not in data):
                return f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            return "Data unavailable"
        
        @callback(
            Output("page-content", "children"),
            [Input("url", "pathname"),
             Input("dashboard-data", "data"),
             Input("selected-guild-id", "data")]
        )
        def render_page_content(pathname, data, guild_id):
            """Render different page content based on the URL path."""
            # Show login page if not authenticated and auth is required
            if self.require_auth and not current_user.is_authenticated:
                return self._create_login_page()
                
            if not data or (isinstance(data, dict) and 'error' in data):
                return self._create_error_page(data.get('error') if data else "Data unavailable")
            
            # Route to the correct page based on URL path
            if pathname == "/":
                return self._create_overview_page(data, guild_id)
            elif pathname == "/messages":
                return self._create_messages_page(data, guild_id)
            elif pathname == "/users":
                return self._create_users_page(data, guild_id)
            elif pathname == "/files":
                return self._create_files_page(data, guild_id)
            elif pathname == "/ai":
                return self._create_ai_page(data, guild_id)
            
            # Default: 404 page
            return self._create_404_page()
    
    def _create_login_page(self):
        """Create a login page for unauthenticated users."""
        return dbc.Container([
            html.Div([
                html.H1("Discord Bot Dashboard", className="display-4 text-center mb-4"),
                html.Div([
                    html.P("Please log in with Discord to access the dashboard.", className="lead text-center mb-4"),
                    dbc.Button(
                        [html.I(className="fab fa-discord me-2"), "Login with Discord"],
                        href="/login",
                        color="primary",
                        size="lg",
                        className="mx-auto d-block"
                    )
                ], className="p-5 bg-dark rounded")
            ], className="d-flex align-items-center justify-content-center", 
               style={"min-height": "80vh"})
        ], fluid=True)
    
    def _create_error_page(self, error_msg):
        """Create an error page when data is unavailable."""
        return dbc.Container([
            html.H1("Error"),
            html.P(f"An error occurred: {error_msg}"),
            dbc.Alert("The dashboard encountered an error while retrieving data. "
                     "Please check the bot logs for more information.", color="danger")
        ])
    
    def _create_404_page(self):
        """Create a 404 page for invalid URLs."""
        return dbc.Container([
            html.H1("404 - Page Not Found"),
            html.P("The page you requested does not exist.")
        ])
    
    def _create_overview_page(self, data, guild_id):
        """Create the overview dashboard page with key metrics."""
        stats = data.get('statistics', {})
        guild_name = self._get_guild_name(guild_id)
        
        # Create info cards
        info_cards = dbc.Row([
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{stats.get('total_messages', 0):,}", className="card-title text-center"),
                    html.P("Total Messages", className="card-text text-center")
                ])
            ], color="primary", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{stats.get('unique_users', 0):,}", className="card-title text-center"),
                    html.P("Unique Users", className="card-text text-center")
                ])
            ], color="success", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{stats.get('total_files', 0):,}", className="card-title text-center"),
                    html.P("Files Stored", className="card-text text-center")
                ])
            ], color="warning", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{stats.get('total_ai_interactions', 0):,}", className="card-title text-center"),
                    html.P("AI Interactions", className="card-text text-center")
                ])
            ], color="info", inverse=True), width=3)
        ], className="mb-4")
        
        # Create activity chart
        daily_message_counts = stats.get('daily_message_counts', {})
        if daily_message_counts:
            df_messages = pd.DataFrame(list(daily_message_counts.items()), columns=['date', 'count'])
            df_messages['date'] = pd.to_datetime(df_messages['date'])
            
            message_fig = px.line(
                df_messages, 
                x='date', 
                y='count', 
                title='Message Activity (Last 30 Days)',
                labels={'date': 'Date', 'count': 'Message Count'}
            )
            message_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            activity_graph = dcc.Graph(figure=message_fig)
        else:
            activity_graph = html.Div("No message activity data available.")
        
        # Recent messages table
        recent_messages = data.get('recent_messages', [])
        if recent_messages:
            message_rows = []
            for i, msg in enumerate(recent_messages[:10]):  # Limit to 10 most recent messages
                timestamp = datetime.fromisoformat(msg['timestamp']) if 'timestamp' in msg else None
                formatted_time = timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "Unknown"
                
                # Truncate content for display
                content = msg.get('content', '')
                if len(content) > 100:
                    content = content[:97] + '...'
                
                message_rows.append(html.Tr([
                    html.Td(f"{i+1}"),
                    html.Td(msg.get('author_name', 'Unknown')),
                    html.Td(content),
                    html.Td(formatted_time)
                ]))
            
            recent_messages_table = dbc.Table([
                html.Thead(html.Tr([
                    html.Th("#"),
                    html.Th("User"),
                    html.Th("Message"),
                    html.Th("Time")
                ])),
                html.Tbody(message_rows)
            ], striped=True, bordered=True, hover=True, responsive=True, className="mt-4")
        else:
            recent_messages_table = html.Div("No recent messages available.")
        
        return dbc.Container([
            html.H1(f"Dashboard Overview: {guild_name}", className="my-4"),
            info_cards,
            dbc.Row([
                dbc.Col(activity_graph, width=12)
            ], className="mb-4"),
            dbc.Row([
                dbc.Col([
                    html.H3("Recent Messages"),
                    recent_messages_table
                ], width=12)
            ])
        ])
    
    def _get_guild_name(self, guild_id):
        """Get the name of a guild from its ID"""
        if guild_id == "demo":
            return "Demo Guild"
            
        if not self.require_auth or not current_user.is_authenticated:
            return f"Guild {guild_id}"
            
        # Check in user's guilds
        for guild in current_user.guilds:
            if str(guild.get('id')) == str(guild_id):
                return guild.get('name', f"Guild {guild_id}")
                
        # If bot client is available, check there
        if hasattr(self.message_monitor, 'client') and hasattr(self.message_monitor.client, 'guilds'):
            for guild in self.message_monitor.client.guilds:
                if str(guild.id) == str(guild_id):
                    return guild.name
                    
        return f"Guild {guild_id}"

    def _invalidate_cache_for_guild(self, guild_id):
        """Invalidate cache for a specific guild."""
        if guild_id in self.cache['dashboard_data']:
            self.cache['dashboard_data'][guild_id] = {
                'data': None,
                'timestamp': 0
            }
    
    def start(self):
        """Start the dashboard server in a separate thread."""
        if self.running:
            logger.warning("Dashboard is already running")
            return
        
        def run_server():
            logger.info(f"Starting dashboard server on {self.host}:{self.port}")
            self.app.run(
                host=self.host,
                port=self.port,
                debug=self.debug,
                use_reloader=False  # Disable reloader to avoid duplicate processes
            )
        
        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()
        self.running = True
        
        logger.info(f"Dashboard server started at http://{self.host}:{self.port}")
        return f"http://{self.host}:{self.port}"
    
    def stop(self):
        """Stop the dashboard server."""
        if not self.running:
            logger.warning("Dashboard is not running")
            return
        
        self.running = False
        # Note: This won't actually terminate the Flask server
        # For a cleaner shutdown, a production implementation would use a proper
        # signal handler or WSGI server with shutdown capabilities
        
        logger.info("Dashboard server stopping (note: thread may continue until main process exits)")
        
    def _create_messages_page(self, data, guild_id):
        """Create the messages dashboard page with message metrics and visualizations."""
        stats = data.get('statistics', {})
        message_stats = data.get('message_statistics', {})
        guild_name = self._get_guild_name(guild_id)
        
        # Create message info cards
        info_cards = dbc.Row([
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{stats.get('total_messages', 0):,}", className="card-title text-center"),
                    html.P("Total Messages", className="card-text text-center")
                ])
            ], color="primary", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{message_stats.get('avg_daily_messages', 0):,.1f}", className="card-title text-center"),
                    html.P("Avg. Daily Messages", className="card-text text-center")
                ])
            ], color="success", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{message_stats.get('avg_message_length', 0):,.1f}", className="card-title text-center"),
                    html.P("Avg. Message Length", className="card-text text-center")
                ])
            ], color="warning", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{message_stats.get('total_channels', 0):,}", className="card-title text-center"),
                    html.P("Active Channels", className="card-text text-center")
                ])
            ], color="info", inverse=True), width=3)
        ], className="mb-4")
        
        # Message activity by time of day
        hourly_data = message_stats.get('hourly_activity', {})
        if hourly_data:
            df_hourly = pd.DataFrame(list(hourly_data.items()), columns=['hour', 'count'])
            df_hourly['hour'] = df_hourly['hour'].astype(int)
            df_hourly = df_hourly.sort_values('hour')
            
            hourly_fig = px.bar(
                df_hourly, 
                x='hour', 
                y='count', 
                title='Message Activity by Hour of Day',
                labels={'hour': 'Hour (24h format)', 'count': 'Message Count'}
            )
            hourly_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            hourly_activity_graph = dcc.Graph(figure=hourly_fig)
        else:
            hourly_activity_graph = html.Div("No hourly activity data available.")

        # Message activity by day of week
        weekday_data = message_stats.get('weekday_activity', {})
        if weekday_data:
            # Convert numeric weekday to name
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            df_weekday = pd.DataFrame(list(weekday_data.items()), columns=['weekday', 'count'])
            df_weekday['weekday'] = df_weekday['weekday'].astype(int)
            df_weekday['weekday_name'] = df_weekday['weekday'].apply(lambda x: day_names[x % 7])
            df_weekday = df_weekday.sort_values('weekday')
            
            weekday_fig = px.bar(
                df_weekday, 
                x='weekday_name', 
                y='count', 
                title='Message Activity by Day of Week',
                labels={'weekday_name': 'Day', 'count': 'Message Count'}
            )
            weekday_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            weekday_activity_graph = dcc.Graph(figure=weekday_fig)
        else:
            weekday_activity_graph = html.Div("No weekday activity data available.")
        
        # Channel activity
        channel_data = message_stats.get('channel_activity', {})
        if channel_data:
            df_channel = pd.DataFrame(list(channel_data.items()), columns=['channel', 'count'])
            df_channel = df_channel.sort_values('count', ascending=False).head(10)  # Top 10 channels
            
            channel_fig = px.bar(
                df_channel, 
                x='channel', 
                y='count', 
                title='Top 10 Most Active Channels',
                labels={'channel': 'Channel', 'count': 'Message Count'}
            )
            channel_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            channel_activity_graph = dcc.Graph(figure=channel_fig)
        else:
            channel_activity_graph = html.Div("No channel activity data available.")
            
        # Recent messages table (reuse from overview page)
        recent_messages = data.get('recent_messages', [])
        if recent_messages:
            message_rows = []
            for i, msg in enumerate(recent_messages[:15]):  # Show more messages on this page
                timestamp = datetime.fromisoformat(msg['timestamp']) if 'timestamp' in msg else None
                formatted_time = timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "Unknown"
                channel_name = msg.get('channel_name', 'Unknown Channel')
                
                # Truncate content for display
                content = msg.get('content', '')
                if len(content) > 100:
                    content = content[:97] + '...'
                
                message_rows.append(html.Tr([
                    html.Td(f"{i+1}"),
                    html.Td(msg.get('author_name', 'Unknown')),
                    html.Td(channel_name),
                    html.Td(content),
                    html.Td(formatted_time)
                ]))
            
            recent_messages_table = dbc.Table([
                html.Thead(html.Tr([
                    html.Th("#"),
                    html.Th("User"),
                    html.Th("Channel"),
                    html.Th("Message"),
                    html.Th("Time")
                ])),
                html.Tbody(message_rows)
            ], striped=True, bordered=True, hover=True, responsive=True, className="mt-4")
        else:
            recent_messages_table = html.Div("No recent messages available.")
            
        return dbc.Container([
            html.H1(f"Message Activity: {guild_name}", className="my-4"),
            info_cards,
            dbc.Row([
                dbc.Col(hourly_activity_graph, md=6),
                dbc.Col(weekday_activity_graph, md=6)
            ], className="mb-4"),
            dbc.Row([
                dbc.Col(channel_activity_graph, width=12)
            ], className="mb-4"),
            dbc.Row([
                dbc.Col([
                    html.H3("Recent Messages"),
                    recent_messages_table
                ], width=12)
            ])
        ])
    
    def _create_users_page(self, data, guild_id):
        """Create the users dashboard page with user engagement metrics and visualizations."""
        stats = data.get('statistics', {})
        user_stats = data.get('user_statistics', {})
        guild_name = self._get_guild_name(guild_id)
        
        # Create user info cards
        info_cards = dbc.Row([
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{stats.get('unique_users', 0):,}", className="card-title text-center"),
                    html.P("Total Users", className="card-text text-center")
                ])
            ], color="primary", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{user_stats.get('daily_active_users', 0):,}", className="card-title text-center"),
                    html.P("Daily Active Users", className="card-text text-center")
                ])
            ], color="success", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{user_stats.get('weekly_active_users', 0):,}", className="card-title text-center"),
                    html.P("Weekly Active Users", className="card-text text-center")
                ])
            ], color="warning", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{user_stats.get('new_users_last_week', 0):,}", className="card-title text-center"),
                    html.P("New Users (Last Week)", className="card-text text-center")
                ])
            ], color="info", inverse=True), width=3)
        ], className="mb-4")
        
        # User activity over time
        user_activity = user_stats.get('user_activity_trends', {})
        if user_activity:
            df_activity = pd.DataFrame(list(user_activity.items()), columns=['date', 'active_users'])
            df_activity['date'] = pd.to_datetime(df_activity['date'])
            df_activity = df_activity.sort_values('date')
            
            activity_fig = px.line(
                df_activity, 
                x='date', 
                y='active_users', 
                title='Daily Active Users (Last 30 Days)',
                labels={'date': 'Date', 'active_users': 'Active Users'}
            )
            activity_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            user_activity_graph = dcc.Graph(figure=activity_fig)
        else:
            user_activity_graph = html.Div("No user activity trend data available.")

        # Most active users
        active_users = user_stats.get('most_active_users', {})
        if active_users:
            df_users = pd.DataFrame(list(active_users.items()), columns=['user', 'message_count'])
            df_users = df_users.sort_values('message_count', ascending=False).head(10)  # Top 10 users
            
            users_fig = px.bar(
                df_users, 
                x='user', 
                y='message_count', 
                title='Top 10 Most Active Users',
                labels={'user': 'User', 'message_count': 'Message Count'}
            )
            users_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            active_users_graph = dcc.Graph(figure=users_fig)
        else:
            active_users_graph = html.Div("No active user data available.")

        # User roles distribution
        role_distribution = user_stats.get('role_distribution', {})
        if role_distribution:
            df_roles = pd.DataFrame(list(role_distribution.items()), columns=['role', 'count'])
            
            roles_fig = px.pie(
                df_roles, 
                values='count', 
                names='role', 
                title='User Role Distribution',
                hole=0.3  # Donut chart
            )
            roles_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            roles_graph = dcc.Graph(figure=roles_fig)
        else:
            roles_graph = html.Div("No role distribution data available.")
        
        # User engagement metrics
        engagement_metrics = user_stats.get('engagement_metrics', {})
        if engagement_metrics:
            metrics_table = dbc.Table([
                html.Thead(html.Tr([
                    html.Th("Metric"),
                    html.Th("Value")
                ])),
                html.Tbody([
                    html.Tr([html.Td("Average Messages per User"), html.Td(f"{engagement_metrics.get('avg_messages_per_user', 0):.2f}")]),
                    html.Tr([html.Td("Average Message Length"), html.Td(f"{engagement_metrics.get('avg_message_length', 0):.2f} chars")]),
                    html.Tr([html.Td("Users with Command Usage"), html.Td(f"{engagement_metrics.get('users_with_commands', 0):,}")]),
                    html.Tr([html.Td("Users with Reactions"), html.Td(f"{engagement_metrics.get('users_with_reactions', 0):,}")]),
                    html.Tr([html.Td("Retention Rate (30 days)"), html.Td(f"{engagement_metrics.get('retention_rate', 0):.1f}%")])
                ])
            ], striped=True, bordered=True, hover=True, responsive=True, className="mt-4")
        else:
            metrics_table = html.Div("No engagement metrics available.")
        
        return dbc.Container([
            html.H1(f"User Engagement: {guild_name}", className="my-4"),
            info_cards,
            dbc.Row([
                dbc.Col(user_activity_graph, width=12)
            ], className="mb-4"),
            dbc.Row([
                dbc.Col(active_users_graph, md=6),
                dbc.Col(roles_graph, md=6)
            ], className="mb-4"),
            dbc.Row([
                dbc.Col([
                    html.H3("User Engagement Metrics"),
                    metrics_table
                ], width=12)
            ])
        ])
    
    def _create_files_page(self, data, guild_id):
        """Create the files dashboard page with file & media metrics and visualizations."""
        stats = data.get('statistics', {})
        file_stats = data.get('file_statistics', {})
        guild_name = self._get_guild_name(guild_id)
        
        # Create file info cards
        info_cards = dbc.Row([
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{stats.get('total_files', 0):,}", className="card-title text-center"),
                    html.P("Total Files", className="card-text text-center")
                ])
            ], color="primary", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{file_stats.get('total_storage', 0):.2f} MB", className="card-title text-center"),
                    html.P("Total Storage Used", className="card-text text-center")
                ])
            ], color="success", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{file_stats.get('images_count', 0):,}", className="card-title text-center"),
                    html.P("Images", className="card-text text-center")
                ])
            ], color="warning", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{file_stats.get('videos_count', 0):,}", className="card-title text-center"),
                    html.P("Videos", className="card-text text-center")
                ])
            ], color="info", inverse=True), width=3)
        ], className="mb-4")
        
        # File type distribution pie chart
        file_types = file_stats.get('file_types', {})
        if file_types:
            df_types = pd.DataFrame(list(file_types.items()), columns=['file_type', 'count'])
            
            types_fig = px.pie(
                df_types, 
                values='count', 
                names='file_type', 
                title='File Type Distribution',
                hole=0.3  # Donut chart
            )
            types_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            file_types_graph = dcc.Graph(figure=types_fig)
        else:
            file_types_graph = html.Div("No file type distribution data available.")

        # File uploads over time
        uploads_over_time = file_stats.get('uploads_over_time', {})
        if uploads_over_time:
            df_uploads = pd.DataFrame(list(uploads_over_time.items()), columns=['date', 'count'])
            df_uploads['date'] = pd.to_datetime(df_uploads['date'])
            df_uploads = df_uploads.sort_values('date')
            
            uploads_fig = px.line(
                df_uploads, 
                x='date', 
                y='count', 
                title='File Uploads Over Time',
                labels={'date': 'Date', 'count': 'Number of Files'}
            )
            uploads_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            uploads_graph = dcc.Graph(figure=uploads_fig)
        else:
            uploads_graph = html.Div("No file upload trend data available.")
        
        # File size distribution
        size_distribution = file_stats.get('size_distribution', {})
        if size_distribution:
            # Convert size categories to ordered categories
            size_categories = [
                '0-100KB', '100KB-1MB', '1MB-5MB', '5MB-10MB', '10MB-50MB', '50MB+'
            ]
            
            # Ensure all categories exist, fill with zeros if missing
            size_data = {cat: size_distribution.get(cat, 0) for cat in size_categories}
            
            df_sizes = pd.DataFrame(list(size_data.items()), columns=['size_range', 'count'])
            df_sizes['size_range'] = pd.Categorical(df_sizes['size_range'], categories=size_categories, ordered=True)
            df_sizes = df_sizes.sort_values('size_range')
            
            sizes_fig = px.bar(
                df_sizes, 
                x='size_range', 
                y='count', 
                title='File Size Distribution',
                labels={'size_range': 'Size Range', 'count': 'Number of Files'}
            )
            sizes_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            sizes_graph = dcc.Graph(figure=sizes_fig)
        else:
            sizes_graph = html.Div("No file size distribution data available.")
        
        # Recent files table
        recent_files = file_stats.get('recent_files', [])
        if recent_files:
            file_rows = []
            for i, file in enumerate(recent_files[:10]):
                timestamp = datetime.fromisoformat(file['uploaded_at']) if 'uploaded_at' in file else None
                formatted_time = timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "Unknown"
                
                file_size = file.get('size_bytes', 0)
                if file_size < 1024:
                    size_str = f"{file_size} B"
                elif file_size < 1024 * 1024:
                    size_str = f"{file_size/1024:.1f} KB"
                else:
                    size_str = f"{file_size/(1024*1024):.1f} MB"
                
                file_rows.append(html.Tr([
                    html.Td(f"{i+1}"),
                    html.Td(file.get('filename', 'Unknown')),
                    html.Td(file.get('type', 'Unknown')),
                    html.Td(size_str),
                    html.Td(file.get('uploader', 'Unknown')),
                    html.Td(formatted_time)
                ]))
            
            recent_files_table = dbc.Table([
                html.Thead(html.Tr([
                    html.Th("#"),
                    html.Th("Filename"),
                    html.Th("Type"),
                    html.Th("Size"),
                    html.Th("Uploader"),
                    html.Th("Date")
                ])),
                html.Tbody(file_rows)
            ], striped=True, bordered=True, hover=True, responsive=True, className="mt-4")
        else:
            recent_files_table = html.Div("No recent files available.")
            
        return dbc.Container([
            html.H1(f"Files & Media: {guild_name}", className="my-4"),
            info_cards,
            dbc.Row([
                dbc.Col(file_types_graph, md=6),
                dbc.Col(sizes_graph, md=6)
            ], className="mb-4"),
            dbc.Row([
                dbc.Col(uploads_graph, width=12)
            ], className="mb-4"),
            dbc.Row([
                dbc.Col([
                    html.H3("Recently Uploaded Files"),
                    recent_files_table
                ], width=12)
            ])
        ])
    
    def _create_ai_page(self, data, guild_id):
        """Create the AI dashboard page with AI interaction metrics and visualizations."""
        stats = data.get('statistics', {})
        ai_stats = data.get('ai_statistics', {})
        guild_name = self._get_guild_name(guild_id)
        
        # Create AI info cards
        info_cards = dbc.Row([
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{stats.get('total_ai_interactions', 0):,}", className="card-title text-center"),
                    html.P("Total AI Interactions", className="card-text text-center")
                ])
            ], color="primary", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{ai_stats.get('unique_users', 0):,}", className="card-title text-center"),
                    html.P("Unique Users", className="card-text text-center")
                ])
            ], color="success", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{ai_stats.get('avg_response_time', 0):.2f}s", className="card-title text-center"),
                    html.P("Avg. Response Time", className="card-text text-center")
                ])
            ], color="warning", inverse=True), width=3),
            
            dbc.Col(dbc.Card([
                dbc.CardBody([
                    html.H4(f"{ai_stats.get('satisfaction_rate', 0):.1f}%", className="card-title text-center"),
                    html.P("Satisfaction Rate", className="card-text text-center")
                ])
            ], color="info", inverse=True), width=3)
        ], className="mb-4")
        
        # AI usage over time
        ai_usage = ai_stats.get('usage_over_time', {})
        if ai_usage:
            df_usage = pd.DataFrame(list(ai_usage.items()), columns=['date', 'count'])
            df_usage['date'] = pd.to_datetime(df_usage['date'])
            df_usage = df_usage.sort_values('date')
            
            usage_fig = px.line(
                df_usage, 
                x='date', 
                y='count', 
                title='AI Interactions Over Time',
                labels={'date': 'Date', 'count': 'Number of Interactions'}
            )
            usage_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            usage_graph = dcc.Graph(figure=usage_fig)
        else:
            usage_graph = html.Div("No AI usage trend data available.")

        # AI request types
        request_types = ai_stats.get('request_types', {})
        if request_types:
            df_types = pd.DataFrame(list(request_types.items()), columns=['type', 'count'])
            df_types = df_types.sort_values('count', ascending=False)
            
            types_fig = px.pie(
                df_types, 
                values='count', 
                names='type', 
                title='AI Request Types',
                hole=0.3  # Donut chart
            )
            types_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            types_graph = dcc.Graph(figure=types_fig)
        else:
            types_graph = html.Div("No AI request type data available.")
        
        # Top AI users
        top_users = ai_stats.get('top_users', {})
        if top_users:
            df_users = pd.DataFrame(list(top_users.items()), columns=['user', 'count'])
            df_users = df_users.sort_values('count', ascending=False).head(10)  # Top 10 users
            
            users_fig = px.bar(
                df_users, 
                x='user', 
                y='count', 
                title='Top 10 AI Users',
                labels={'user': 'User', 'count': 'Interaction Count'}
            )
            users_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            users_graph = dcc.Graph(figure=users_fig)
        else:
            users_graph = html.Div("No top AI users data available.")
        
        # Average response times
        response_times = ai_stats.get('response_times', {})
        if response_times:
            df_times = pd.DataFrame(list(response_times.items()), columns=['date', 'avg_time'])
            df_times['date'] = pd.to_datetime(df_times['date'])
            df_times = df_times.sort_values('date')
            
            times_fig = px.line(
                df_times, 
                x='date', 
                y='avg_time', 
                title='Average AI Response Times',
                labels={'date': 'Date', 'avg_time': 'Avg. Response Time (s)'}
            )
            times_fig.update_layout(
                template="plotly_dark",
                plot_bgcolor='rgba(50, 50, 50, 0.1)',
                paper_bgcolor='rgba(50, 50, 50, 0.1)'
            )
            
            times_graph = dcc.Graph(figure=times_fig)
        else:
            times_graph = html.Div("No response time data available.")
            
        # Recent AI interactions
        recent_interactions = ai_stats.get('recent_interactions', [])
        if recent_interactions:
            interaction_rows = []
            for i, interaction in enumerate(recent_interactions[:10]):
                timestamp = datetime.fromisoformat(interaction['timestamp']) if 'timestamp' in interaction else None
                formatted_time = timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "Unknown"
                
                # Truncate content for display
                prompt = interaction.get('prompt', '')
                if len(prompt) > 80:
                    prompt = prompt[:77] + '...'
                
                response = interaction.get('response', '')
                if len(response) > 80:
                    response = response[:77] + '...'
                
                interaction_rows.append(html.Tr([
                    html.Td(f"{i+1}"),
                    html.Td(interaction.get('user', 'Unknown')),
                    html.Td(prompt),
                    html.Td(response),
                    html.Td(f"{interaction.get('response_time', 0):.2f}s"),
                    html.Td(formatted_time)
                ]))
            
            recent_interactions_table = dbc.Table([
                html.Thead(html.Tr([
                    html.Th("#"),
                    html.Th("User"),
                    html.Th("Prompt"),
                    html.Th("Response"),
                    html.Th("Time (s)"),
                    html.Th("Date")
                ])),
                html.Tbody(interaction_rows)
            ], striped=True, bordered=True, hover=True, responsive=True, className="mt-4")
        else:
            recent_interactions_table = html.Div("No recent AI interactions available.")
            
        # Token usage statistics
        token_usage = ai_stats.get('token_usage', {})
        if token_usage:
            metrics_table = dbc.Table([
                html.Thead(html.Tr([
                    html.Th("Metric"),
                    html.Th("Value")
                ])),
                html.Tbody([
                    html.Tr([html.Td("Total Tokens Used"), html.Td(f"{token_usage.get('total_tokens', 0):,}")]),
                    html.Tr([html.Td("Prompt Tokens"), html.Td(f"{token_usage.get('prompt_tokens', 0):,}")]),
                    html.Tr([html.Td("Completion Tokens"), html.Td(f"{token_usage.get('completion_tokens', 0):,}")]),
                    html.Tr([html.Td("Avg. Tokens per Request"), html.Td(f"{token_usage.get('avg_tokens_per_request', 0):.1f}")]),
                    html.Tr([html.Td("Estimated Cost"), html.Td(f"${token_usage.get('estimated_cost', 0):.2f}")])
                ])
            ], striped=True, bordered=True, hover=True, responsive=True, className="mt-4")
        else:
            metrics_table = html.Div("No token usage data available.")
        
        return dbc.Container([
            html.H1(f"AI Interactions: {guild_name}", className="my-4"),
            info_cards,
            dbc.Row([
                dbc.Col(usage_graph, width=12)
            ], className="mb-4"),
            dbc.Row([
                dbc.Col(types_graph, md=6),
                dbc.Col(users_graph, md=6)
            ], className="mb-4"),
            dbc.Row([
                dbc.Col(times_graph, width=12)
            ], className="mb-4"),
            dbc.Row([
                dbc.Col([
                    html.H3("Token Usage Statistics"),
                    metrics_table
                ], width=12)
            ], className="mb-4"),
            dbc.Row([
                dbc.Col([
                    html.H3("Recent AI Interactions"),
                    recent_interactions_table
                ], width=12)
            ])
        ])