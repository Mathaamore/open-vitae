"""Isolated UI fixture: no provider, external network or candidate account."""
from unittest.mock import Mock
from job_agent import app as module, opportunities, sources

module.providers=Mock()
module.providers.status.side_effect=AssertionError('Offline workflow probed a provider')
module.providers.complete.side_effect=AssertionError('Offline workflow called an AI')
module.providers.cached=None
sources.json_request=Mock(side_effect=ValueError('No network connection. Your saved work is still available.'))
opportunities.request=Mock(side_effect=ValueError('No network connection.'))
app=module.app
