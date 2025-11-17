from app import create_app, db
from app.models.team import Department, TeamMember, AuditLog

app = create_app()

with app.app_context():
    db.create_all()
    print("✅ Team tables created successfully!")
