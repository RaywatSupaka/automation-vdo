import os
import sys
import unittest
from unittest.mock import patch

from core.membership import (DevelopmentMembership, Membership, MembershipError,
                             _development_membership_enabled, production_membership)


class MemoryStore:
    def load(self):
        return ''

    def save(self, value):
        pass

    def delete(self):
        pass


class DevelopmentMembershipTests(unittest.TestCase):
    def test_dev_mode_requires_explicit_flag_source_checkout_and_unfrozen_runtime(self):
        with patch.dict(os.environ, {'SMARTFLOW_DEV_BYPASS_MEMBERSHIP': '1'}), \
                patch('core.membership._development_checkout', return_value=True), \
                patch.object(sys, 'frozen', False, create=True):
            self.assertTrue(_development_membership_enabled('development'))
            self.assertFalse(_development_membership_enabled('0.15.486'))
            with patch.object(sys, 'frozen', True):
                self.assertFalse(_development_membership_enabled('development'))
        with patch.dict(os.environ, {'SMARTFLOW_DEV_BYPASS_MEMBERSHIP': '1'}), \
                patch('core.membership._development_checkout', return_value=False):
            self.assertFalse(_development_membership_enabled('development'))
        with patch.dict(os.environ, {}, clear=True), \
                patch('core.membership._development_checkout', return_value=True):
            self.assertFalse(_development_membership_enabled('development'))

    def test_dev_member_never_uses_vault_or_membership_server(self):
        with patch.dict(os.environ, {'SMARTFLOW_DEV_BYPASS_MEMBERSHIP': '1'}), \
                patch('core.membership._development_checkout', return_value=True), \
                patch.object(sys, 'frozen', False, create=True), \
                patch('core.secure_store.WindowsCredentialStore', side_effect=AssertionError('vault used')), \
                patch('core.membership.request_server', side_effect=AssertionError('server used')):
            member = production_membership('development')
            self.assertIsInstance(member, DevelopmentMembership)
            member.start()
            member.require()
            self.assertTrue(member.status()['dev_mode'])
            self.assertTrue(member.status()['desktop']['allowed'])
            self.assertFalse(member.status()['extension']['allowed'])
            with self.assertRaises(MembershipError):
                member.login('not-a-token')
            with self.assertRaises(MembershipError):
                member.logout()
            member.close()

    def test_production_factory_stays_locked_even_when_flag_is_set(self):
        with patch.dict(os.environ, {'SMARTFLOW_DEV_BYPASS_MEMBERSHIP': '1'}), \
                patch('core.membership._development_checkout', return_value=True), \
                patch('core.secure_store.WindowsCredentialStore', return_value=MemoryStore()):
            with patch.object(sys, 'frozen', True, create=True):
                frozen = production_membership('development')
            release = production_membership('0.15.486')
        for member in (frozen, release):
            self.assertIsInstance(member, Membership)
            self.assertFalse(member.allowed())
            with self.assertRaises(MembershipError):
                member.require()


if __name__ == '__main__':
    unittest.main()
