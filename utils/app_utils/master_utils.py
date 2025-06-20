
def master_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_master():
            flash('You do not have permission to access this page.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/master')
@login_required
@master_required
def master_dashboard():
    # Get all master's students
    students = User.query.filter_by(
        class_code=current_user.class_code,
        role=Role.STUDENT
    ).all()
    return render_template('master/dashboard.html', students=students)

@app.route('/master/users')
@login_required
@master_required
def master_users():
    students = User.query.filter_by(
        class_code=current_user.class_code,
        role=Role.STUDENT
    ).all()
    return render_template('master/users.html', students=students)

@app.route('/master/user/<int:user_id>')
@login_required
@master_required
def master_user_detail(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_master:
        flash('Cannot view master user details.')
        return redirect(url_for('master_users'))

    # Get message history between master and student
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user.id)) |
        ((Message.sender_id == user.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.desc()).all()

    return render_template('master/user_detail.html', user=user, messages=messages)

@app.route('/master/user/<int:user_id>/progress')
@login_required
@master_required
def master_user_progress(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_master:
        flash('Cannot view master user progress.')
        return redirect(url_for('master_users'))
    progress_data = Progress.query.filter_by(user_id=user.id).all()
    return render_template('master/user_progress.html', user=user, progress_data=progress_data)

@app.route('/master/user/<int:user_id>/update-belt', methods=['POST'])
@login_required
@master_required
def master_update_belt(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_master:
        flash('Cannot modify master user.')
        return redirect(url_for('master_users'))

    new_belt = request.form.get('belt_rank')
    if new_belt in ['White', 'Yellow', 'Green', 'Blue', 'Red', 'Black']:
        user.belt_rank = new_belt
        db.session.commit()
        flash('Belt rank updated successfully.')
    else:
        flash('Invalid belt rank.')

    return redirect(url_for('master_user_detail', user_id=user_id))

@app.route('/master/user/<int:user_id>/send-message', methods=['POST'])
@login_required
@master_required
def master_send_message(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_master:
        flash('Cannot send message to master user.')
        return redirect(url_for('master_users'))

    content = request.form.get('message')
    if not content:
        flash('Message cannot be empty.')
        return redirect(url_for('master_dashboard'))

    # Create new message
    message = Message(
        sender_id=current_user.id,
        receiver_id=user.id,
        content=content
    )

    db.session.add(message)
    db.session.commit()

    flash('Message sent successfully.')
    return redirect(url_for('master_dashboard'))

@app.route('/master/user/<int:user_id>/download-csv')
@login_required
@master_required
def master_download_csv(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_master:
        flash('Cannot download master data.')
        return redirect(url_for('master_users'))

    # Create CSV data
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(['Date', 'Activity Type', 'Details'])

    # Write activity data
    for activity in user.activities:
        writer.writerow([
            activity.activity_date.strftime('%Y-%m-%d'),
            activity.activity_type,
            activity.details if activity.details else ''
        ])

    # Create the response
    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={user.username}_activity.csv'
        }
    )