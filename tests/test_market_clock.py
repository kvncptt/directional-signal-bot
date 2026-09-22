import unittest
from datetime import datetime
from directional_bot.market_clock import snapshot

class ClockTest(unittest.TestCase):
    def test_overlap_and_boundaries(self):
        d=snapshot(datetime.fromisoformat('2026-09-22T12:00:00+00:00'))
        now=d['generated_at'];names={w['name'] for w in d['windows'] if w['start']<=now<w['end']}
        self.assertEqual(names,{'London','New York'})
        self.assertTrue(any(set(o['names'])==names and o['start']<=now<o['end'] for o in d['overlaps']))
    def test_saturday_is_closed(self):
        d=snapshot(datetime.fromisoformat('2026-09-26T12:00:00+00:00'))
        self.assertFalse(any(w['start']<=d['generated_at']<w['end'] for w in d['windows']))
    def test_dst_mismatch(self):
        # US has changed; UK has not yet changed in March.
        d=snapshot(datetime.fromisoformat('2026-03-16T12:00:00+00:00'))
        starts={w['key']:datetime.fromtimestamp(w['start'],datetime.fromisoformat('2026-03-16T00:00:00+00:00').tzinfo).hour for w in d['windows'] if datetime.fromtimestamp(w['start'],datetime.fromisoformat('2026-03-16T00:00:00+00:00').tzinfo).date().isoformat()=='2026-03-16'}
        self.assertEqual(starts['london'],8);self.assertEqual(starts['newyork'],12)
        self.assertEqual(starts['tokyo'],0);self.assertEqual(starts['sydney'],21)
