import unittest
from datetime import datetime,timedelta
from directional_bot.london import bucket,summarize,next_open

class LondonTest(unittest.TestCase):
    def test_close_boundary_and_weekend(self):
        self.assertEqual(bucket('2026-09-22T08:00:00+00:00').hour,8)
        self.assertIsNone(bucket('2026-09-22T07:00:00+00:00'))
        self.assertEqual(bucket('2026-09-22T16:00:00+00:00').hour,16)
        self.assertIsNone(bucket('2026-09-22T16:01:00+00:00'))
        self.assertIsNone(bucket('2026-09-26T09:00:00+00:00'))
    def test_dst_open(self):
        summer=next_open(datetime.fromisoformat('2026-09-22T04:00:00+00:00'))
        winter=next_open(datetime.fromisoformat('2026-12-22T04:00:00+00:00'))
        self.assertEqual(summer.utcoffset(),timedelta(hours=1))
        self.assertEqual(winter.utcoffset(),timedelta(0))
        self.assertEqual(winter.hour,8)
    def test_complete_gap_and_missing(self):
        start=datetime.fromisoformat('2026-09-22T07:00:00+00:00')
        candles=[dict(timestamp=(start+timedelta(minutes=i)).isoformat(),symbol='EUR_USD',open=1.1,high=1.1002,low=1.0999,close=1.1001) for i in range(1,61)]
        s=summarize(start,candles,start+timedelta(hours=1))
        self.assertEqual(s['status'],'complete');self.assertAlmostEqual(s['change_pips'],1)
        self.assertEqual(summarize(start,candles[:-1],start+timedelta(hours=1))['status'],'incomplete')
        self.assertEqual(summarize(start,[],start+timedelta(hours=1),'EUR_USD')['status'],'missing')
