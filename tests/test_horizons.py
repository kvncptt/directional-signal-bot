import unittest
from directional_bot.horizons import compare, attach


def trade(a,b,admission='APPROVED',symbol='A',version=None):
    return dict(result_1m=a,result_3m=b,admission=admission,symbol=symbol,trend_context={'quality_version':version})


class HorizonTests(unittest.TestCase):
    def test_matched_only_and_ties(self):
        result=compare([trade('WIN','LOSS'),trade('TIE','WIN'),trade('WIN',None),trade('WIN','LOSS','BLOCKED'),trade('WIN','LOSS','BASELINE')])
        self.assertEqual(result['n'],2)
        self.assertEqual(result['unresolved'],1)
        self.assertEqual(result['rates'],{'1':.5,'3':.5})
        self.assertIsNone(result['leader'])
        self.assertEqual(result['only_1m_wins'],1)
        self.assertEqual(result['only_3m_wins'],1)

    def test_versions_and_pair_disagreement(self):
        state={'quality_policy':{},'strategies':[{'id':'07','strategy_id':'08','pair':'A','trades':[trade('WIN','LOSS'),trade('LOSS','WIN',version='quality-v2')]},{'id':'08','strategy_id':'08','pair':'B','trades':[trade('LOSS','WIN',symbol='B')]}]}
        state['quality_policy']={'effective_at':'now'}
        a=attach(state)['horizon_analysis']['08']
        self.assertEqual(a['current'],'quality-v2')
        self.assertEqual(a['cohorts']['quality-v2']['overall']['n'],1)
        self.assertTrue(a['cohorts']['trend-v1']['overall']['pair_disagreement'])
        self.assertEqual(a['cohorts']['quality-v2']['overall']['leader'],3)

    def test_unchanged_strategy_is_not_split(self):
        state={'quality_policy':{'active':True},'strategies':[{'id':'01','pair':'A','trades':[trade('WIN','LOSS'),trade('WIN','LOSS',version='quality-v2')]}]}
        a=attach(state)['horizon_analysis']['01']
        self.assertEqual(a['cohorts']['trend-v1']['overall']['n'],2)
