# HappyBirthdayBot

misskey.io上で動作するBotです。
http://misskey.io/@HBDBot 　として活動中。

アンテナで指定したキーワードを含むノートに関して、

・:happy_birth_day__i: のリアクションがついている
・投稿したユーザーの誕生日が今日

のどちらかの条件でリアクション、リノートによる拡散を行います。
フォロワーの誕生日を記憶し、０時になった時にお誕生日をお祝いする機能もあります。

This is a bot program for misskey.io.
Currently working as http://misskey.io/@HBDBot

When it sees a note which includes specified keywords (eg. birthday),
it checks the reactions on the note and user's birthday.
If the condition matches, it renotes (reposts) the note.

It also remembers followers' birthday and celebrates birthday boys & girls.
