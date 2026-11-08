from django.urls import reverse

from flashdeck.models import ClaimedAnswer


def test_the_admin_pages_load(client, user, etre):
    client.force_login(user)
    for model in ("subject", "deck", "card", "claimedanswer"):
        url = reverse(f"admin:flashdeck_{model}_changelist")
        assert client.get(url).status_code == 200
    url = reverse("admin:flashdeck_card_change", args=[etre.pk])
    assert client.get(url).status_code == 200


def test_claims_are_accepted_in_the_admin(client, user, dog):
    answer = dog.answers.get()
    claimed = ClaimedAnswer.objects.create(answer=answer, user=user, text="un chien")
    client.force_login(user)
    client.post(
        reverse("admin:flashdeck_claimedanswer_changelist"),
        {"action": "accept", "_selected_action": [claimed.pk]},
    )
    claimed.refresh_from_db()
    assert claimed.status == "accepted"
    assert "un chien" in answer.__class__.objects.get(pk=answer.pk).accepted()
