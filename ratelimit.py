import time
from datetime import datetime, timedelta

post_log = []
def rate_limit(limit_ph=60, limit_pm=10, post_rate=1):
    '''APIの送信に自主的なレートリミットを設けます。
    デコレートされた関数は区別なくカウントされます。
    レート制限中は処理を完全に止めます。'''
    global post_log
    def _rate_limit(func):
        def rate_limit_wrapper(*args, **kwargs):
            while last_hour() >= limit_ph:
                print('____レート制限中（時）____')
                print('解除はだいたい', post_log[0]+timedelta(hours=1))
                td = post_log[0]+timedelta(hours=1) - datetime.now()
                time.sleep(td.seconds+60)
            while last_minute() >= limit_pm:
                print('____レート制限中（分）____')
                print('解除はだいたい', post_log[0]+timedelta(minutes=2))
                td = post_log[-limit_pm]+timedelta(minutes=2) - datetime.now()
                time.sleep(td.seconds+60)
            func(*args, **kwargs)
            post_log.append(datetime.now())
            time.sleep(post_rate)
        return rate_limit_wrapper
    return _rate_limit

def last_hour():
    global post_log
    post_log = [t for t in post_log \
                if t+timedelta(hours=1) > datetime.now()]
    return len(post_log)

def last_minute():
    global post_log
    minut = [t for t in post_log \
             if t+timedelta(minutes=1) > datetime.now()]
    return len(minut)

class TestMethods:
    @rate_limit(limit_ph=10, limit_pm=5)
    def note(self, text):
        print('N:',text)
    @rate_limit(limit_ph=10, limit_pm=5)
    def react(self):
        print('reaction')

if __name__ == '__main__':
    tm = TestMethods()
    while msg := input('RでRN、その他は投稿'):
        if msg == 'R':
            tm.react()
        else:
            tm.note(msg)
        print([t.strftime('%H:%M') for t in post_log])


