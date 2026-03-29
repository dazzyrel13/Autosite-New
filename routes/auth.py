"""
Authentication routes.
"""

from flask import render_template, jsonify, redirect, url_for, current_app
from flask_login import login_user, login_required, logout_user
from forms import LoginForm
from models import User


from werkzeug.security import check_password_hash

from extensions import limiter

def register_auth_routes(app):
    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit("5 per minute")
    def login():
        form = LoginForm()
        if form.validate_on_submit():
            username = form.username.data
            password = form.password.data
            admin_user = current_app.config['ADMIN_USER']
            admin_pass_hash = current_app.config['ADMIN_PASS'] # Now expecting this to be a hash
            
            # Strict scrypt hash check for admin security
            if username == admin_user and admin_pass_hash.startswith('scrypt:'):
                if check_password_hash(admin_pass_hash, password):
                    login_user(User(admin_user))
                    return jsonify(success=True)
            return jsonify(success=False, message="Неверный логин или пароль")
        return render_template('login.html', form=form)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))