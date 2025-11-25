from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import PermissionDenied


class KUDomainSocialAccountAdapter(DefaultSocialAccountAdapter):
    allowed_domain = 'ku.th'

    def _has_allowed_domain(self, email: str) -> bool:
        return bool(email and email.lower().endswith(f'@{self.allowed_domain}'))

    def pre_social_login(self, request, sociallogin):
        email = sociallogin.user.email
        if not self._has_allowed_domain(email):
            raise PermissionDenied('Please sign in with your @ku.th Google account.')
        super().pre_social_login(request, sociallogin)

    def is_open_for_signup(self, request, sociallogin):
        return self._has_allowed_domain(sociallogin.user.email)
