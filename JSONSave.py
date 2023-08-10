import json

class JSONSave:

    @staticmethod
    def save(file_name: str, **kwargs) -> None:
        '''filenameにJSON形式で任意のデータを書き込みます。ファイルが無ければ作ります。'''
        try:
            f = open(file_name, 'w')
            print('ファイルを上書きします', file_name)
        except FileNotFoundError:
            f = open(file_name, 'x')
            print('ファイルを作ります', file_name)
        json.dump(kwargs, f, indent=2)
        f.close()

    @staticmethod
    def load(file_name: str) -> dict:
        '''filenameをJSON形式で読み込んで辞書型で返します。'''
        try:
            with open(file_name, "r") as f:
                try:
                    jsondata = json.load(f)
                except json.JSONDecodeError:
                    print('JSONの解読に失敗しました。')
                    return
        except FileNotFoundError:
            print('JSONファイルが存在しません。')
            return
        print('データの読み込みに成功しました。')
        return jsondata
