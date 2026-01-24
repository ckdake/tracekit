from tracekit.activity import Activity


def test_activity_creation_with_data():
    """Test creating an Activity with initial data."""
    am = Activity(name="Test Ride", distance=10.5, activity_type="Ride", equipment="Road Bike")

    assert am.name == "Test Ride"
    assert am.distance == 10.5
    assert am.activity_type == "Ride"
    assert am.equipment == "Road Bike"
