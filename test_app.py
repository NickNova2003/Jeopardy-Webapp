import io, json, os, tempfile, unittest

tmp=tempfile.TemporaryDirectory(); os.environ['JEOPARDY_DATA_DIR']=tmp.name
import app

def call(path, method='GET', payload=None, body=b'', content_type='application/json', headers=None):
    if payload is not None: body=json.dumps(payload).encode()
    env={'REQUEST_METHOD':method,'PATH_INFO':path,'CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':content_type,'wsgi.input':io.BytesIO(body)}
    env.update(headers or {}); result={}
    def start(status, hdrs): result.update(status=status,headers=dict(hdrs))
    result['body']=b''.join(app.application(env,start)); return result

class AppTest(unittest.TestCase):
    def setUp(self): app.init_db()
    def test_crud_game(self):
        payload={'title':'Test','contestants':[{'id':'p','name':'Nikhil','score':0}],'categories':[],'clues':[]}
        made=call('/api/games','POST',payload); self.assertTrue(made['status'].startswith('201'))
        gid=json.loads(made['body'])['id']; got=call('/api/games/'+gid)
        self.assertEqual(json.loads(got['body'])['title'],'Test')
        payload['title']='Changed'; self.assertTrue(call('/api/games/'+gid,'PUT',payload)['status'].startswith('200'))
        self.assertTrue(call('/api/games/'+gid,'DELETE')['status'].startswith('200'))
    def test_upload_validation(self):
        bad=call('/api/upload','POST',body=b'x',content_type='text/plain',headers={'HTTP_X_FILENAME':'x.txt'})
        self.assertTrue(bad['status'].startswith('415'))
        good=call('/api/upload','POST',body=b'abc',content_type='audio/mpeg',headers={'HTTP_X_FILENAME':'x.mp3'})
        self.assertTrue(good['status'].startswith('201'))
        media=json.loads(good['body'])
        partial=call(media['url'],headers={'HTTP_RANGE':'bytes=1-2'})
        self.assertTrue(partial['status'].startswith('206'))
        self.assertEqual(partial['body'],b'bc')
        self.assertEqual(partial['headers']['Content-Range'],'bytes 1-2/3')
        self.assertEqual(partial['headers']['Accept-Ranges'],'bytes')
        invalid=call(media['url'],headers={'HTTP_RANGE':'bytes=9-12'})
        self.assertTrue(invalid['status'].startswith('416'))
    def test_final_jeopardy_is_persisted(self):
        final={'category':'World History','question':'A final clue','answer':'A final response','played':False}
        made=call('/api/games','POST',{'title':'Final test','contestants':[],'categories':[],'clues':[],'finalJeopardy':final})
        gid=json.loads(made['body'])['id']; saved=json.loads(call('/api/games/'+gid)['body'])
        self.assertEqual(saved['finalJeopardy']['category'],'World History')

    def test_spoilers_and_multiple_slides_are_persisted(self):
        clue={
            'id':'q1','categoryId':'c1','value':200,
            'question':'This [[hidden phrase]] is clickable','answer':'Response',
            'questionSlides':[{'id':'s2','text':'Second slide','media':None}],
            'answerSlides':[{'id':'a2','text':'More explanation','media':None}],
            'used':False
        }
        made=call('/api/games','POST',{
            'title':'Slides test','contestants':[],
            'categories':[{'id':'c1','name':'Test'}],'clues':[clue]
        })
        gid=json.loads(made['body'])['id']; saved=json.loads(call('/api/games/'+gid)['body'])
        self.assertEqual(saved['clues'][0]['question'],'This [[hidden phrase]] is clickable')
        self.assertEqual(saved['clues'][0]['questionSlides'][0]['text'],'Second slide')
        self.assertEqual(saved['clues'][0]['answerSlides'][0]['text'],'More explanation')

if __name__=='__main__': unittest.main()
