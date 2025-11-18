# app.py
import os

from datetime import datetime, date, timedelta

from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from sqlalchemy import or_
from models import db, Guest, Admin, Room, Reservation
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/room_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    """Checks if a file extension is allowed."""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def payment(reservation_id, user_id, amount, payment_method, payment_status):

    pass


def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_very_secret_and_complex_key')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///resort.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    db.init_app(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        if user_id.startswith('admin_'):
            admin_id = user_id.split('_')[1]
            return Admin.query.get(int(admin_id))
        try:
            return Guest.query.get(int(user_id))
        except ValueError:
            return None

    with app.app_context():
        db.create_all()

        if not Admin.query.filter_by(username='admin').first():
            admin_user = Admin(username='admin')
            admin_user.set_password('admin')
            db.session.add(admin_user)
            db.session.commit()
            print("Initial Admin created: username='admin', password='admin'")

    def is_admin():
        """Checks if the currently logged-in user is an Admin."""
        return current_user.is_authenticated and isinstance(current_user, Admin)

    def admin_required(func):
        """Decorator to enforce admin access."""

        def wrapper(*args, **kwargs):
            if not is_admin():
                flash('Access denied: Admin privileges required.', 'danger')
                return redirect(url_for('index'))
            return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        return wrapper

    from flask import jsonify

    @app.route('/room_availability/<int:room_id>')
    def room_availability(room_id):
        """Return JSON of booked dates for a room (to show in the calendar)."""
        reservations = Reservation.query.filter_by(room_id=room_id).filter(
            Reservation.status.in_(['Reserved', 'Completed'])
        ).all()

        booked_dates = []
        for res in reservations:
            current = res.check_in
            while current < res.check_out:
                booked_dates.append(current.strftime('%Y-%m-%d'))
                current = current.replace(day=current.day + 1) if current.day < 28 else current + timedelta(days=1)

        return jsonify(booked_dates)




    @app.context_processor
    def inject_user_utilities():
        """Makes utilities like is_admin() available to all Jinja templates."""
        return dict(is_admin=is_admin, datetime=datetime, date=date)

    def is_room_available(room_id, check_in_str, check_out_str):
        try:
            check_in = datetime.strptime(check_in_str, '%Y-%m-%d').date()
            check_out = datetime.strptime(check_out_str, '%Y-%m-%d').date()
        except ValueError:
            return False, "Invalid date format."

        if check_out <= check_in:
            return False, "Check-out date must be after check-in date."

        if check_in < date.today():
            return False, "Check-in date cannot be in the past."

        conflicting_reservations = Reservation.query.filter(
            Reservation.room_id == room_id,
            Reservation.status.in_(['Reserved', 'Completed']),
            Reservation.check_in < check_out,
            Reservation.check_out > check_in
        ).first()

        if conflicting_reservations:
            return False, "The room is already booked for these dates."

        return True, (check_in, check_out)

    @app.route('/')
    def index():
        rooms = Room.query.all()
        return render_template('index.html', rooms=rooms)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            if is_admin():
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('index'))

        if request.method == 'POST':
            email_or_username = request.form.get('email_or_username')
            password = request.form.get('password')

            user = Guest.query.filter_by(email=email_or_username).first()
            if user and user.check_password(password):
                login_user(user)
                flash('Logged in as Guest!', 'success')
                return redirect(request.args.get('next') or url_for('index'))

            admin_user = Admin.query.filter_by(username=email_or_username).first()
            if admin_user and admin_user.check_password(password):
                login_user(admin_user)
                flash('Logged in as Admin!', 'success')
                return redirect(request.args.get('next') or url_for('admin_dashboard'))

            flash('Invalid email/username or password.', 'danger')

        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')

            if Guest.query.filter_by(email=email).first():
                flash('Email already registered.', 'danger')
                return redirect(url_for('register'))

            new_guest = Guest(name=name, email=email)
            new_guest.set_password(password)
            db.session.add(new_guest)
            db.session.commit()

            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

        return render_template('register.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('You have been logged out.', 'info')
        return redirect(url_for('index'))

    @app.route('/reserve/<int:room_id>', methods=['GET', 'POST'])
    @login_required
    def make_reservation(room_id):
        if is_admin():
            flash("Admins cannot make guest reservations.", 'warning')
            return redirect(url_for('admin_dashboard'))

        room = Room.query.get_or_404(room_id)

        if request.method == 'POST':
            check_in_str = request.form.get('check_in')
            check_out_str = request.form.get('check_out')

            is_available, result = is_room_available(room_id, check_in_str, check_out_str)


            if is_available:
                check_in_date, check_out_date = result
                # Calculate number of nights
                num_nights = (check_out_date - check_in_date).days
                amount_due = num_nights * room.price

            if is_available:
                check_in_date, check_out_date = result
                new_reservation = Reservation(
                    guest_id=current_user.id,
                    room_id=room.id,
                    check_in=check_in_date,
                    check_out=check_out_date,
                    status='Reserved',
                )

                db.session.add(new_reservation)
                db.session.commit()
                flash(f'Reservation for Room {room.room_number} confirmed from {check_in_str} to {check_out_str}.',
                      'success')


                return redirect(url_for('my_reservations'))
            else:
                flash(f'Reservation failed: {result}', 'danger')

        return render_template('reservation.html', room=room)


    @app.route('/my_reservations')
    @login_required
    def my_reservations():
        if is_admin():
            return redirect(url_for('admin_dashboard'))

        reservations = Reservation.query.filter_by(guest_id=current_user.id).order_by(Reservation.check_in.desc()).all()
        return render_template('guest_reservations.html', reservations=reservations, today=date.today())

    @app.route('/cancel_reservation/<int:res_id>', methods=['POST'])
    @login_required
    def cancel_reservation(res_id):
        reservation = Reservation.query.get_or_404(res_id)

        if not is_admin() and reservation.guest_id != current_user.id:
            flash('Access denied: You can only cancel your own reservations.', 'danger')
            return redirect(url_for('my_reservations'))

        if reservation.status == 'Reserved' and reservation.check_in > date.today():
            reservation.status = 'Cancelled'
            db.session.commit()
            flash(f'Reservation #{res_id} for Room {reservation.room.room_number} has been cancelled.', 'success')
        else:
            flash('This reservation cannot be cancelled (already completed, cancelled, or check-in passed).', 'warning')

        if is_admin():
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('my_reservations'))

    @app.route('/admin')
    @login_required
    @admin_required
    def admin_dashboard():
        rooms = Room.query.all()
        reservations = Reservation.query.order_by(Reservation.check_in.desc()).all()
        return render_template('admin_dashboard.html', rooms=rooms, reservations=reservations, today=date.today())

    @app.route('/admin/add_room', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def add_room():
        if request.method == 'POST':
            room_number = request.form.get('room_number')
            room_type = request.form.get('room_type')
            price = request.form.get('price')

            image_file = request.files.get('image_file')
            image_filename = None

            if not room_number or not room_type or not price:
                flash('All required room fields are missing.', 'danger')
                return redirect(url_for('add_room'))

            if Room.query.filter_by(room_number=room_number).first():
                flash(f'Room number {room_number} already exists.', 'danger')
                return redirect(url_for('add_room'))

            try:
                price_float = float(price)
            except ValueError:
                flash('Price must be a valid number.', 'danger')
                return redirect(url_for('add_room'))

            if image_file and allowed_file(image_file.filename):
                filename = secure_filename(image_file.filename)

                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                file_extension = filename.rsplit('.', 1)[1].lower()
                image_filename = f'{room_number}_{timestamp}.{file_extension}'

                save_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                image_file.save(save_path)
            elif image_file and image_file.filename != '':
                flash('Invalid file type. Allowed extensions are: png, jpg, jpeg, jfif, gif, avif.', 'danger')
                return redirect(url_for('add_room'))

            new_room = Room(
                room_number=room_number,
                room_type=room_type,
                price=price_float,
                status='Available',
                image_file=image_filename
            )
            db.session.add(new_room)
            db.session.commit()
            flash(f'Room {room_number} added successfully.', 'success')
            return redirect(url_for('admin_dashboard'))

        return render_template('add_edit_room.html', title='Add Room', room=None)

    @app.route('/admin/edit_room/<int:room_id>', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def edit_room(room_id):
        room = Room.query.get_or_404(room_id)

        if request.method == 'POST':
            room_number = request.form.get('room_number')
            room_type = request.form.get('room_type')
            price = request.form.get('price')
            status = request.form.get('status')

            image_file = request.files.get('image_file')

            existing_room = Room.query.filter(
                Room.room_number == room_number,
                Room.id != room_id
            ).first()

            if existing_room:
                flash(f'Room number {room_number} already exists for another room.', 'danger')
                return redirect(url_for('edit_room', room_id=room_id))

            try:
                price_float = float(price)
            except ValueError:
                flash('Price must be a valid number.', 'danger')
                return redirect(url_for('edit_room', room_id=room_id))

            if image_file and allowed_file(image_file.filename):
                if room.image_file:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], room.image_file)
                    if os.path.exists(old_path):
                        os.remove(old_path)

                filename = secure_filename(image_file.filename)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                file_extension = filename.rsplit('.', 1)[1].lower()
                image_filename = f'{room_number}_{timestamp}.{file_extension}'

                save_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                image_file.save(save_path)
                room.image_file = image_filename
            elif image_file and image_file.filename != '':
                flash('Invalid file type. Allowed extensions are: png, jpg, jpeg, gif.', 'danger')
                return redirect(url_for('edit_room', room_id=room_id))

            room.room_number = room_number
            room.room_type = room_type
            room.price = price_float
            room.status = status

            db.session.commit()
            flash(f'Room {room_number} updated successfully.', 'success')
            return redirect(url_for('admin_dashboard'))

        return render_template('add_edit_room.html', title='Edit Room', room=room)

    @app.route('/about')
    def about():
        return render_template('about.html', title='About Us')

    @app.route('/contact')
    def contact():
        return render_template('contact.html', title='Contact Us')

    @app.route('/admin/delete_room/<int:room_id>', methods=['POST'])
    @login_required
    @admin_required
    def delete_room(room_id):
        room = Room.query.get_or_404(room_id)

        active_reservations = Reservation.query.filter(
            Reservation.room_id == room_id,
            Reservation.status == 'Reserved'
        ).count()

        if active_reservations > 0:
            flash(f'Cannot delete Room {room.room_number}: {active_reservations} active reservations found.', 'danger')
            return redirect(url_for('admin_dashboard'))

        if room.image_file:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], room.image_file)
            if os.path.exists(image_path):
                os.remove(image_path)

        db.session.delete(room)
        db.session.commit()
        flash(f'Room {room.room_number} and all associated data deleted successfully.', 'success')
        return redirect(url_for('admin_dashboard'))

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)




