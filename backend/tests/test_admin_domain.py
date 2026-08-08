import pytest
from app import models, email

def test_admin_get_and_update_site_domain(client, get_db_session):
    db = get_db_session()

    # 1. Fetch default settings endpoint
    res = client.get("/api/admin/settings")
    assert res.status_code == 200
    data = res.json()
    assert "site_domain" in data
    assert data["site_domain"] == ""

    # 2. Directly insert site_domain setting into DB
    setting = db.query(models.SiteSetting).filter(models.SiteSetting.key == "site_domain").first()
    if not setting:
        setting = models.SiteSetting(key="site_domain", value="https://social.example.com")
        db.add(setting)
    else:
        setting.value = "https://social.example.com"
    db.commit()

    # Verify site_domain returned in GET /api/admin/settings
    res2 = client.get("/api/admin/settings")
    assert res2.status_code == 200
    assert res2.json()["site_domain"] == "https://social.example.com"

    # 3. Test get_frontend_url helper
    frontend_url = email.get_frontend_url(db)
    assert frontend_url == "https://social.example.com"

    # 4. Test domain without http/https auto-prepends http:// and strips trailing slash
    setting.value = "myfqdn.org/"
    db.commit()

    assert email.get_frontend_url(db) == "http://myfqdn.org"
