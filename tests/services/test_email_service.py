from avanamy.services.email_service import EmailService


class DummyProvider:
    def __init__(self):
        self.calls = []

    def send(self, to, subject, html_body, from_email, from_name):
        self.calls.append(
            {
                "to": to,
                "subject": subject,
                "html_body": html_body,
                "from_email": from_email,
                "from_name": from_name,
            }
        )
        return True


def test_send_invitation_email_builds_links_and_subject(monkeypatch):
    monkeypatch.setenv("EMAIL_FROM", "noreply@example.com")
    monkeypatch.setenv("EMAIL_FROM_NAME", "Avanamy Test")
    monkeypatch.setenv("FRONTEND_URL", "https://frontend.test")

    service = EmailService()
    dummy = DummyProvider()
    service.provider = dummy

    result = service.send_invitation_email(
        to_email="invitee@example.com",
        inviter_name="Inviter One",
        organization_name="Test Org",
        invitation_token="token-xyz"
    )

    assert result is True
    assert len(dummy.calls) == 1
    call = dummy.calls[0]
    assert call["to"] == "invitee@example.com"
    assert "Inviter One invited you to join Test Org" in call["subject"]
    assert call["from_email"] == "noreply@example.com"
    assert call["from_name"] == "Avanamy Test"
    assert "https://frontend.test/invitations/accept?token=token-xyz" in call["html_body"]
    assert "https://frontend.test/invitations/decline?token=token-xyz" in call["html_body"]


def test_send_email_returns_false_without_provider(monkeypatch):
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    service = EmailService()
    service.provider = None

    result = service._send_email(
        to="nobody@example.com",
        subject="Subject",
        html_body="<p>Body</p>"
    )

    assert result is False
