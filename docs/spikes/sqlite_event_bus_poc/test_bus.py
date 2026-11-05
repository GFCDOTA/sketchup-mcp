import tempfile
import threading
import unittest
from pathlib import Path
from bus import Bus,process_one

class TestBus(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.bus=Bus(Path(self.tmp.name)/'events.db')
 def tearDown(self): self.tmp.cleanup()
 def test_end_to_end_real_subprocess(self):
  self.bus.publish('pr:1:sha:abc:implement','IMPLEMENT',{'text':'  Hello World '})
  self.assertTrue(process_one(self.bus,'IMPLEMENT','claude-worker'))
  artifact=__import__('json').loads(self.bus.rows()[0]['result'])['artifact']
  self.bus.publish('pr:1:sha:abc:review','REVIEW',{'artifact':artifact,'expected':'hello-world'})
  self.assertTrue(process_one(self.bus,'REVIEW','codex-worker'))
  self.assertEqual(__import__('json').loads(self.bus.rows()[1]['result'])['verdict'],'APPROVE')
 def test_dedup_and_restart(self):
  id1=self.bus.publish('a','IMPLEMENT',{'text':'A B'})
  self.assertEqual(id1,self.bus.publish('a','IMPLEMENT',{'text':'INJECT'}))
  self.bus=Bus(self.bus.path)
  self.assertEqual(len(self.bus.rows()),1)
  self.assertTrue(process_one(self.bus,'IMPLEMENT','worker'))
  self.assertFalse(process_one(self.bus,'IMPLEMENT','worker'))
 def test_lease_recovery_and_stale_owner(self):
  self.bus.publish('b','IMPLEMENT',{'text':'Hello'})
  old=self.bus.claim('IMPLEMENT','old',lease_seconds=1,now=100)
  self.assertIsNone(self.bus.claim('IMPLEMENT','new',now=100.5))
  new=self.bus.claim('IMPLEMENT','new',now=102)
  self.assertEqual(old['id'],new['id'])
  self.assertFalse(self.bus.finish(old,'old','stale',now=102))
  self.assertTrue(self.bus.finish(new,'new','ok',now=102))
 def test_dead_letter(self):
  self.bus.publish('c','IMPLEMENT',{'fail':True,'text':'bad'})
  for _ in range(3):
   self.assertTrue(process_one(self.bus,'IMPLEMENT','worker'))
   __import__('time').sleep(0.12)
  self.assertEqual(self.bus.rows()[0]['state'],'DLQ')
 def test_atomic_claim_two_consumers(self):
  self.bus.publish('d','REVIEW',{'artifact':'a','expected':'a'})
  claimed=[]
  def take(n): claimed.append(self.bus.claim('REVIEW',str(n)))
  threads=[threading.Thread(target=take,args=(i,)) for i in range(2)]
  for t in threads:t.start()
  for t in threads:t.join()
  self.assertEqual(sum(x is not None for x in claimed),1)

if __name__=='__main__': unittest.main()
