import tempfile,unittest
from pathlib import Path
import app
class BugTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.db=Path(self.temp.name)/'bugs.db';app.initialize(self.db)
 def tearDown(self):self.temp.cleanup()
 def test_create_assign_priority_and_lifecycle(self):
  bug=app.create_bug({'title':'Broken save','description':'Save action fails','priority':'critical','assignee':'Demo Dev'},self.db)
  self.assertEqual(bug['status'],'new');self.assertEqual(bug['priority'],'critical')
  changed=app.update_bug(bug['id'],{'status':'in progress','priority':'high','assignee':'Sample Owner'},self.db)
  self.assertEqual((changed['status'],changed['priority'],changed['assignee']),('in progress','high','Sample Owner'))
  self.assertEqual(app.update_bug(bug['id'],{'status':'resolved'},self.db)['status'],'resolved')
 def test_comments_filters_and_detail(self):
  bug=app.create_bug({'title':'Search panel','description':'Text is clipped','priority':'high'},self.db)
  comment=app.add_comment(bug['id'],{'author':'Demo Reviewer','body':'Confirmed in demo.'},self.db)
  self.assertEqual(comment['bug_id'],bug['id']);self.assertEqual(len(app.bug_detail(bug['id'],self.db)['comments']),1)
  rows=app.list_bugs({'status':'new','priority':'high','q':'clipped'},self.db);self.assertEqual([x['id'] for x in rows],[bug['id']])
  self.assertEqual(app.list_bugs({'assignee':'Unassigned'},self.db)[0]['id'],bug['id'])
 def test_validation_and_unknown_issue(self):
  with self.assertRaises(ValueError):app.create_bug({'title':'','description':'d'},self.db)
  bug=app.create_bug({'title':'Valid','description':'details'},self.db)
  with self.assertRaises(ValueError):app.update_bug(bug['id'],{'status':'invalid'},self.db)
  with self.assertRaises(KeyError):app.add_comment(999,{'body':'x'},self.db)
 def test_demo_issues_are_seeded(self):self.assertGreaterEqual(len(app.list_bugs(path=self.db)),3)
if __name__=='__main__':unittest.main()
