# ## HappyBirthDayBot on Misskey.io
# ### 仕様
# - Misskey.ioのアンテナ上で特定のリアクションが一定数ついているノートをReNoteする。
# - ただし昨日以前のノートなら無視する。
# - ユーザーのIDリストを一日保持し、同じユーザを二度以上ReNoteしないようにする。
# - なるべくサーバーに迷惑をかけない。レートリミットに引っかからないようにする。
# - 一時間ごとに変数の中身をJSONテキストに保存する

from misskey import Misskey, NoteVisibility, exceptions, MiAuth
from datetime import date, datetime, timedelta, timezone
import time
import random
from requests import ReadTimeout

from ratelimit import rate_limit
from JSONSave import JSONSave

_silent_mode = False
# サイレントモード：投稿やリアクションを一切行わず、
# 通知とTLのチェックのみ行ってリストを更新してすぐ終了します。
# 強制終了などで保存できなかったデータを回収する時に使います。

JST = timezone(timedelta(hours=9), "JST")
FILE_NAME = "variables.json"
VERSION = "ver 0.5 beta test"
ADMIN = ""

def has_past(dt, **kwargs) -> bool:
    """時刻dtから指定の時間が経ったかどうかを返します。

    Args:
        dt (str|datetime): 時刻を表す文字列かdatetime型
        **kwargs: timedelta()に渡すキーワード(ex: hours=1)

    Returns:
        bool: 結果
    """
    if type(dt) is str:
        dt = datetime.fromisoformat(dt)
    return dt+timedelta(**kwargs) < datetime.now()

#Misskey.pyの関数補完
class Misskey_Antenna(Misskey):

    def notes_antennas(
        self,
        antenna_id: str,
        limit: int = 10,
        sinceId = None,
        untilId = None,
        sinceDate = None,
        untilDate = None
        ):
        '''antenna_idで指定したアンテナのノートを返します。'''
        params = Misskey._Misskey__params(locals())
        print(params)
        return self._Misskey__request_api(endpoint_name='antennas/notes', **params)
    
    def notes_timeline(
        self,
        limit: int = 10,
        sinceId = None,
        untilId = None,
        sinceDate = None,
        untilDate = None
    ):
        params = Misskey._Misskey__params(locals())
        return self._Misskey__request_api(endpoint_name='notes/timeline', **params)
        
    def notes_reactions_create(self, *args, **kwargs):
        try:
            if not _silent_mode:
                super().notes_reactions_create(*args,**kwargs)
        except exceptions.MisskeyAPIException:
            pass #既にリアクションがついている
        except ReadTimeout:
            print('❗❗❗リアクションタイムアウト❗❗❗')
            pass

    @rate_limit(limit_pm=5)
    def notes_create(self, *args, **kwargs):
        posted = False
        count = 0
        while not posted:
            if count >= 10:
                print('❗❗❗投稿に立て続けに失敗❗❗❗')
                break
            try:
                if not _silent_mode:
                    super().notes_create(*args, **kwargs)
                posted = True
            except ReadTimeout:
                print('❗❗❗投稿タイムアウト❗❗❗')
                time.sleep(60)
                count += 1
                continue
            except exceptions.MisskeyAPIException as e:
                if e.code == 'TIMELINE_HAYASUGI_YABAI':
                    print('タイムライン速すぎヤバイエラー❗')
                print(e)
                time.sleep(60)
                count += 1
                continue

    def dm_admin(self, message):
        print('❗📧', message[:100])
        super().notes_create(
            text="@"+self.admin+' '+message,
            visibility=NoteVisibility.SPECIFIED,
            visible_user_ids=[ADMIN],
            local_only=True)

class TimelineHandler:
    '''タイムラインの取得をコントロールする'''

    def __init__(self,
                 timeline,
                 max_period = timedelta(days=1),
                 refresh_rate = 1.0, #sec
                 batch_size = 10,
                 desc = True,
                 **param
                 ):
        self.timeline = timeline
        self.max_period: timedelta = max_period
        self.refresh_rate: float = refresh_rate
        self.batch_size: int = batch_size
        self.desc: bool = desc
        self.since_id = None
        self.param = param
    
    def get_timeline(self):
        '''Retrun recent updates.'''
        try:
            result = self.timeline(limit=self.batch_size,
                                sinceId=self.since_id,
                                **self.param)
        except ReadTimeout:
            print('❗❗❗TL読み込みタイムアウト❗❗❗')
            return []
        time.sleep(self.refresh_rate)
        if not result:
            return []
        if self.desc:
            self.since_id = result[0]['id']
        else:
            self.since_id = result[-1]['id']
        return result

class NotificationHandler:
    '''通知の取得をコントロールする'''

    def __init__(self,
                 mk,
                 refresh_rate = 1.0, #sec
                 batch_size = 10
                 ):
        self.mk = mk
        self.refresh_rate: float = refresh_rate
        self.batch_size: int = batch_size
        self.since_id = None
    
    def get_notification(self):
        try:
            result = self.mk.i_notifications(
                limit=self.batch_size,
                since_id=self.since_id,
                include_types=('mention', 'reply', 'follow', 'renote', 'quote'))
        except ReadTimeout:
            print('❗❗❗通知読み込みタイムアウト❗❗❗')
            return []
        time.sleep(self.refresh_rate)
        result = [n for n in result if n['id'] != self.since_id]
        if not result:
            return []
        self.since_id = result[0]['id']
        return result

def is_leap_year(year:int) -> bool:
    '''西暦年を入力すると閏年かどうか返します。'''
    if year%400 == 0:
        return True
    if year%100 == 0:
        return False
    if year%4 == 0:
        return True
    return False

class MisskeyUser:
    """ミスキーユーザ"""
    def __init__(self, username, host=None):
        if '@' in username:
            self.username, self.host = username.split("@")
        else:
            self.username = username
            self.host = host
        user_read = False
        while not user_read:
            try:
                if self.host is None:
                    u = Misskey().users_show(username=self.username)
                else:
                    u = Misskey(self.host).users_show(username=self.username)
            except ReadTimeout:
                print('❗❗❗ユーザー情報タイムアウト❗❗❗')
                time.sleep(1)
                continue
            user_read = True
        self.useralias = u['name']
        self.bd = u['birthday']

    @staticmethod
    def from_dict(dict):
        username = dict['username']
        host = dict['host']
        if host is not None:
            sn = dict['instance']['softwareName']
            if sn != 'misskey':
                return
        result = None
        result = MisskeyUser(username, host)
        return result

    
    @property
    def name_w_host(self):
        '''ホストが設定されているならホスト付きのユーザネームを返します。'''
        if self.host is not None:
            return self.username+'@'+self.host
        else:
            return self.username

    def get_bd(self) -> date|None:
        '''date型で誕生日を返す'''
        if self.bd:
            return date.fromisoformat(self.bd)
        return None
    
    def datediff(self) -> int:
        '''今日と誕生日の日付の差を返します。明日なら－１、当日なら０、昨日なら１です。
        2月29日生で今年が平年の場合、3月1日を誕生日として扱います。
        誕生日が設定されていない場合はNoneを返します。'''
        if (birthday := self.get_bd()) is None:
            return None
        dt = date.today()
        bmonth = birthday.month
        bday = birthday.day
        if bmonth == 2 and bday == 29 and not is_leap_year(dt.year):
            bmonth, bday = 3, 1
        result = (dt-date(dt.year, bmonth, bday)).days
        #今が年末で、誕生日が年始の場合
        if result-is_leap_year(dt.year) >= 363:
            result = result-is_leap_year(dt.year) - 365
        #今が年始で、誕生日が年末の場合
        if result+is_leap_year(dt.year) <= -363:
            result = result+is_leap_year(dt.year) + 365
        return result
    
    def is_birthday(self) -> bool:
        '''今日が誕生日かどうかを返します。
        未設定の場合はFalseです。'''
        if self.bd == "":
            return False
        return self.datediff() == 0
    
    @property
    def bd_str(self):
        bd = self.get_bd()
        if bd is None:
            return
        return f"{bd.month}月{bd.day}日"

class HBDConversations:
    '''ボットの会話処理を担う'''

    def __init__(
            self, 
            user: MisskeyUser):
        self.user = user

    def greet(self):
        '''呼びかけ部分の定型文'''
        return f'@{self.user.name_w_host} \n{self.user.useralias}さん　'

    def congrats(self):
        '''お祝い文のランダム化'''
        s1 = [  'お誕生日おめでと！',
                'お誕生日おめでとう！',
                'お誕生日おめでとさん！',
                'たんおめだよ！']
        s2 = [  '楽しい一日になりますように！',
                '一日ハッピーに過ごせますように！',
                '特別な一日になりますように！',
                '一年に一度のお誕生日、いっぱい楽しんでね！']
        s3 = [  '元気にまた一年過ごせますように！',
                'ステキな年になりますように！',
                '望みが叶う一年になりますように！']
        
        result = ":happy_birth_day__i:\n"
        if self.user.is_birthday():
            result += random.choice(s1)+'\n'+random.choice(s2)
        else:
            result += random.choice(s1)+'\n'+random.choice(s3)
        return result
    
    def bdmessage(self):
        '''誕生日を反映したメッセージ'''
        result = ""
        if self.user.get_bd() is None:
            result += "まだプロフィールに誕生日を設定してないみたいだね。\n"
            result += "設定が済んだら「登録して」って話しかけてね！\n"
            result += "（個人情報だから少しサバ読んで設定するのもいいかも）\n"
            result += "お誕生日をお祝いできるのを楽しみにしてるよ！\n"
        elif self.user.datediff() == 0: #誕生日当日
            result += "今日はあなたの誕生日だね！\n"
            result += self.congrats()
        elif self.user.datediff() == 1: #昨日が誕生日
            result += "昨日があなたの誕生日だったんだね！\n"
            result += self.congrats()
        elif self.user.datediff() == 2: #一昨日が誕生日
            result += "一昨日があなたの誕生日だったんだね！\n"
            result += self.congrats()
        elif self.user.datediff() == -1: #明日が誕生日
            result += 'あなたのお誕生日は明日だね！\n'
            result += "お誕生日をお祝いできるのを楽しみにしてるよ！\n"
        else:
            result += f'あなたのお誕生日は{self.bd_str}だね！\n'
            result += "お誕生日をお祝いできるのを楽しみにしてるよ！\n"
        return result

    #フォローされた
    def onFollow(self):
        result = self.greet()
        result += "フォローありがとう！\n"
        result += self.bdmessage()
        return result

    #登録して
    def onRegiser(self):
        result = self.greet()
        if self.user.get_bd() is None:
            result += "誕生日が読み取れなかったみたい。ごめんね。\n"
            result += "プロフ設定してから「登録して」って話しかけてね！"
            print('**********登録時読み取り失敗**********')
        else:
            result += self.bdmessage()
        return result
    
    #祝って
    def onRequest(self):
        return self.greet() + self.congrats()
    
    #/help
    def help(self):
        result = self.greet()+"こんにちは。\n"
        result += "【私の取り扱い説明書】HBDBot "+VERSION+"\n"
        result += "私をフォローするか「登録して」って話しかけると\n"
        result += "プロフィールに設定した誕生日を記憶するよ。\n"
        result += ":happy_birth_day__i:がついているノートを\n"
        result += ":rn:することがあるよ。\n"
        result += "\n【コマンド】\n"
        result += "/ping... 動いているかどうか\n"
        result += "/help... このメッセージを返信するよ\n"
        result += "登録して... 誕生日を記憶するよ\n"
        result += "祝って... お祝いするよ\n"
        return result
    
    #/ping
    def pong(self):
        return "@"+self.user.username+" PONG!"
    
    #/kora
    def kora(self):
        return "@"+ADMIN+" ごめんにゃさい...処理を終了します"
    
    def get_message(self, text):
        if '/ping' in text:
            return self.pong()
        elif '/kora' in text and self.user.username == ADMIN:
            return self.kora()
        elif '祝って' in text:
            return self.onRequest()
        elif '登録して' in text:
            return self.onRegiser()
        elif '/help' in text:
            return self.help()
        else:
            return ""

class HBDBot:
    '''Botのメイン処理を担う'''
    
    def __init__(self):
        self.token = "" #Misskeyトークン
        self.antenna_id = ""
        self.admin = ""
        
        self.target_reaction = ":happy_birth_day__i@.:"#反応するリアクションの種類
        self.threshold = 1 #リアクションがいくつ以上ついていたら反応するか
        self.refresh_rate = 20 #何秒ごとにアンテナを読み込むか
        self.batch_size = 30 #一度に読み込むノートの数

        self.celeb_list = {} #お祝いしたユーザのIDと日時
        self.bd_list = {} #フォロワーのIDと誕生日
        self.responded = []

        self.notification_since_id = None
        self.last_saved = None #データ保存した日時
        print(VERSION)
        self.load()

    def __del__(self):
        pass #self.save()

    def save(self):
        # トークン未設定の場合はロードに失敗したと考えるため、
        # セーブデータの上書きを避けて中断する
        if not self.token:
            print('❗❗❗保存を中断します❗❗❗')
            return
        file_path = __file__[:__file__.rfind('\\')+1] + FILE_NAME
        self.notification_since_id = self.notif.since_id
        dic = self.__dict__.copy()
        del dic['last_saved']
        del dic['mk']
        del dic['antenna']
        del dic['ltl']
        del dic['notif']
        JSONSave.save(
            file_name=file_path,
            **dic
            )
        self.last_saved = datetime.now()

    def load(self):
        """
        設定ファイルの読み込み
        """
        file_path = __file__[:__file__.rfind('\\')+1] + FILE_NAME
        dict = JSONSave.load(file_name=file_path)
        if dict is not None:
            for k, v in dict.items():
                self.__dict__[k] = v
            #データ読み込みチェック
            if 'celeb_list' in dict:
                print('祝ったリスト：', len(dict['celeb_list']))
            if 'bd_list' in dict:
                print('誕生日リスト：', len(dict['bd_list']))
        self.last_saved = datetime.now()
        if not self.token:
            self.init_wizard()
        else:
            print('トークン：', self.token)
            self.mk = Misskey_Antenna(i=self.token)
        global ADMIN
        ADMIN = self.admin

        self.antenna = TimelineHandler(
            self.mk.notes_antennas,
            batch_size=self.batch_size,
            antenna_id=self.antenna_id)
        self.ltl = TimelineHandler(
            self.mk.notes_timeline,
            batch_size=self.batch_size)
        self.notif = NotificationHandler(
            self.mk, 
            batch_size=self.batch_size)
        if self.notification_since_id is not None:
            self.notif.since_id = self.notification_since_id

    def init_wizard(self):
        """
        動作に必要な変数の初期化を対話形式で行う
        """
        print('トークンが未設定です。初期設定を行います。')
        self.token = input('Misskeyのトークンを入力してください。'
                           '空のままEnterで新規発行>>>')
        if not self.token:
            auth = MiAuth(name=__file__[__file__.rfind('\\')+1:])
            url = auth.generate_url()
            print('トークンの新規発行を行います。'
                  'URLをブラウザで開いて下さい。',url)
            input('認証が完了したらEnterで続行>>>')
            self.token = auth.check()
        self.mk = Misskey_Antenna(i=self.token)
        try:
            userinfo = self.mk.i()
        except exceptions.MisskeyAuthorizeFailedException:
            print('トークンが無効です。')
            raise exceptions.MisskeyAuthorizeFailedException
        print(userinfo['name'], 'でログイン中')
        admin = input('管理者のユーザIDは？（@無しで）')
        if admin:
            self.admin = admin
        self.mk.users_show(username=self.admin, )

        antenna = input('監視するアンテナIDを入力して下さい。')
        if antenna:
            self.antenna_id = antenna
        target = input('監視するリアクションを入力してください。'
                       '入力例   :happy_birth_day__i@.:')
        if target:
            self.target_reaction = target
        threshold = int(input('何個以上のリアクションで反応しますか？'
                              '(既定値：1)'))
        if threshold:
            self.threshold = threshold

    @staticmethod
    def summarize_note(note) -> str:
        '''ノートの内容を一行に要約した文字列を返します。'''
        timestamp = datetime.fromisoformat(note['createdAt']) \
                + timedelta(hours=9)
        dt_str = timestamp.strftime("(%y/%m/%d %H:%M)")
        username = note['user']['username'][:10]
        if 'birthday' in note:
            username = '🎂'+username
        if note['user']['host'] is not None:
            username += "@"+note['user']['host']
        text = note['text'][:30].replace('\n', '') if note['text'] is not None else ''
        return dt_str+username+'\t'+text
    
    def check_note(self, note):
        if note['user']['username'] == 'HBDBot':
            return
        #流れてきたのがリノートの場合
        if 'renote' in note:
            print('RN:', end='')
            note = note['renote']
        user = MisskeyUser.from_dict(note['user'])
        if user is None:
            return
        if user.is_birthday():
            note['birthday'] = None
        print(self.summarize_note(note), note['reactions'])
        if self.is_to_renote(note, user):
            self.mk.notes_reactions_create(note['id'], self.target_reaction)
            self.mk.notes_create(renote_id=note['id'])
            print('↑↑↑↑↑↑↑↑🎂 RN 🎂↑↑↑↑↑↑↑↑')
            self.celeb_list[user.name_w_host] = datetime.now().isoformat()

    def antenna_search(self):
        atl = self.antenna.get_timeline()
        if not atl:
            print('アンテナに新着ノートはありません。')
            return
        print(f'アンテナ：{len(atl)}/{self.batch_size}件のノートを読み込み。。。')
        for note in atl:
            self.check_note(note)
        print()

    def ltl_search(self):
        ltl = self.ltl.get_timeline()
        if not ltl:
            print('LTLに新着ノートはありません。')
            return
        print(f'LTL：{len(ltl)}/{self.batch_size}件のノートを読み込み。。。')
        for note in ltl:
            self.check_note(note)
        print()

    def is_to_renote(self, note, user) -> bool:
        '''
        渡されたノートがリノート対象かどうかを判定します。
        - 投稿者がお誕生日！かつまだお祝いしていない（確定リノート）
        - target_reactionがthreshold個以上ついている
        - もしくは本文にtarget_reactionが含まれる
        - 投稿日が今日
        - celeb_listにユーザIDが含まれていない
        - celeb_listに含まれる場合、お祝い日時が今日ではない
        - CWとNSFWがついていない
        '''
        if user.is_birthday() and \
            user.name_w_host not in self.celeb_list:
                return True
        if self.target_reaction not in note['reactions'] or \
            note['reactions'][self.target_reaction] < self.threshold:
            return False
        dt = datetime.fromisoformat(note['createdAt'])+timedelta(hours=9)
        if dt.date() != date.today():
            return False
        if user.name_w_host in self.celeb_list:
            dt = datetime.fromisoformat(self.celeb_list[user.name_w_host])
            if dt.date() == date.today():
                return False
        if note['cw'] is not None:
            return False
        if note['files'] is not None:
            for file in note['files']:
                if 'isSensitive' in file and file['isSensitive']:
                    return False
        return True

    def register(self, user: MisskeyUser):
        '''フォロワーIDと誕生日をリストに格納'''
        if not user.bd:
            return
        host = "@"+user.host if user.host is not None else ''
        self.bd_list[user.username+host] = user.bd

    def notification_check(self):
        '''通知を取得してチェック'''
        notifications = self.notif.get_notification()
        if not notifications:
            print('新着のお知らせはありません。')
            return
        print('新着のお知らせは', len(notifications), '件です。')
        for n in notifications:
            if n['id'] in self.responded:
                print('（済）',end='')
            print(n['id'],n['type'],
                n['user']['name']+"\t"+n['user']['username'],
                n['text'][:30] if 'text' in n else '')
            if n['id'] in self.responded:
                # print("____skip____")
                continue
            if 'user' not in n:
                continue
            self.responded.append(n['id'])
            if 'user' not in n:
                continue
            user = MisskeyUser.from_dict(n['user'])
            if user is None:
                continue
            cv = HBDConversations(user)

            if n['type'] == "mention" or n['type'] == "reply":
                print("Message:", self.summarize_note(n['note']))
                id = n['note']['id']
                text = n['note']['text']
                rep = cv.get_message(text)
                # 他サーバーにリプライしようとするとエラーが出るので
                # 緊急措置！！！
                if user.host is not None:
                    id = None
                if rep:
                    self.mk.notes_create(rep, reply_id=id, visibility=NoteVisibility.FOLLOWERS)
                    print('Reply:'+rep[:100])
                    if '/kora' in text and user.username == self.admin:
                        raise KeyboardInterrupt #強制終了
                    elif '登録して' in text:
                        self.register(user)
                else:
                    print('hmm...?')
                    self.mk.notes_reactions_create(id, ":_question_mark:")
            elif n['type'] == 'follow':
                rep = cv.onFollow()
                self.mk.notes_create(rep)
                print('🎉🎉🎉Follow:'+rep[:100])
                self.register(user)

    def midnight(self):
        '''日付が変わったときの処理'''
        print('--------------------')
        print(date.today())
        print('--------------------')
        self.save()

        self.celeb_list = {u:t for u,t in self.celeb_list.items()
                           if not has_past(t, hours=1)}
        print('リストクリア。残り：', len(self.celeb_list))

        bd_users = []
        for u, d in self.bd_list.items():
            try:
                mu = MisskeyUser(u)
            except exceptions.MisskeyAPIException:
                continue
            if mu.is_birthday():
                bd_users.append(mu)
        for u in bd_users:
            cv = HBDConversations(u)
            message = cv.onRequest()
            self.mk.notes_create(message)
            # self.celeb_list[u.name_w_host]=datetime.now().isoformat()

    def mainloop(self):
        try:
            while True:
                if self.last_saved.date() != date.today():
                    time.sleep(60)
                    self.midnight()
                if has_past(self.last_saved, hours=1):
                    print('\n____AUTOSAVE:',datetime.now(),'____')
                    self.responded = self.responded[-100:]
                    self.antenna.since_id = None
                    self.ltl.since_id = None
                    self.save()
                self.antenna_search()
                self.ltl_search()
                self.notification_check()
                if _silent_mode:
                    print('❗❗❗サイレントモードで起動中❗❗❗')
                    break
                time.sleep(self.refresh_rate)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            self.mk.dm_admin("ぐえー\n"+str(e))
        finally:
            print('終了します。')
            self.save()

if __name__ == '__main__':
    bot = HBDBot()
    bot.mainloop()