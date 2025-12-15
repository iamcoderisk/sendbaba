#!/usr/bin/env python3
"""
Manual Bounce System Test Script
Run: python3 test_bounce_system.py
"""
import sys
sys.path.insert(0, '/opt/sendbaba-staging')

from app.services.bounce_service import BounceService, BounceType, get_bounce_service
import uuid

def test_classification():
    """Test bounce classification"""
    print("\n=== Testing Bounce Classification ===")
    service = BounceService()
    
    tests = [
        ("550 5.1.1 User unknown", "hard"),
        ("452 Mailbox full", "soft"),
        ("Blocked as spam", "spam"),
        ("Complaint received", "complaint"),
    ]
    
    for msg, expected in tests:
        bounce_type, reason, action = service.classify_bounce(msg)
        status = "✅" if bounce_type.value == expected else "❌"
        print(f"  {status} '{msg[:30]}' -> {bounce_type.value} ({reason})")


def test_suppression():
    """Test suppression list operations"""
    print("\n=== Testing Suppression List ===")
    service = get_bounce_service()
    
    test_email = f"test-{uuid.uuid4().hex[:6]}@test.com"
    org_id = "test-org"
    
    # Add
    result = service.add_to_suppression(test_email, org_id, "hard", "Test")
    print(f"  Add: {'✅' if result else '❌'}")
    
    # Check
    is_supp, info = service.is_suppressed(test_email, org_id)
    print(f"  Check: {'✅' if is_supp else '❌'}")
    
    # Remove
    result = service.remove_from_suppression(test_email, org_id)
    print(f"  Remove: {'✅' if result else '❌'}")
    
    # Verify removed
    is_supp, _ = service.is_suppressed(test_email, org_id)
    print(f"  Verify: {'✅' if not is_supp else '❌'}")


def test_bounce_processing():
    """Test full bounce processing"""
    print("\n=== Testing Bounce Processing ===")
    service = get_bounce_service()
    
    # Create a test email record first
    cur = service._get_cursor()
    email_id = str(uuid.uuid4())
    test_recipient = f"bounce-test-{uuid.uuid4().hex[:6]}@example.com"
    org_id = str(uuid.uuid4())
    
    try:
        cur.execute("""
            INSERT INTO emails (id, organization_id, sender, recipient, to_email, subject, status, created_at)
            VALUES (%s, %s, 'test@test.com', %s, %s, 'Test', 'failed', NOW())
        """, (email_id, org_id, test_recipient, test_recipient))
        service.db.commit()
        print(f"  Created test email: {email_id[:8]}...")
        
        # Process bounce
        result = service.process_bounce(
            email_id=email_id,
            error_message="550 5.1.1 User unknown - mailbox not found",
            org_id=org_id
        )
        
        if result.get('success'):
            print(f"  ✅ Bounce processed")
            print(f"     Type: {result.get('bounce_type')}")
            print(f"     Action: {result.get('action')}")
            print(f"     Suppressed: {result.get('suppressed')}")
        else:
            print(f"  ❌ Processing failed: {result.get('error')}")
        
        # Cleanup
        cur.execute("DELETE FROM email_bounces WHERE email_id = %s", (email_id,))
        cur.execute("DELETE FROM emails WHERE id = %s", (email_id,))
        cur.execute("DELETE FROM suppression_list WHERE email = %s", (test_recipient,))
        service.db.commit()
        print(f"  Cleaned up test data")
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        service.db.rollback()


def test_stats():
    """Test bounce statistics"""
    print("\n=== Testing Bounce Statistics ===")
    service = get_bounce_service()
    
    # Use a real org_id from database
    cur = service._get_cursor()
    cur.execute("SELECT id FROM organizations LIMIT 1")
    row = cur.fetchone()
    
    if row:
        org_id = row[0]
        stats = service.get_bounce_stats(org_id, 7)
        print(f"  Total bounces (7 days): {stats.get('total', 0)}")
        print(f"  By type: {stats.get('by_type', {})}")
    else:
        print("  ⚠️ No organizations found")


if __name__ == '__main__':
    print("=" * 60)
    print("SENDBABA BOUNCE SYSTEM TEST")
    print("=" * 60)
    
    test_classification()
    test_suppression()
    test_bounce_processing()
    test_stats()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
