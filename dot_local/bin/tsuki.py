#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
月配列 2-263 タイピング練習
"""

import sqlite3
import random
import time
import os

DB_FILE = os.path.expanduser("~/.tsuki_typing.db")

# 色
C_RED = '\033[31m'
C_GREEN = '\033[32m'
C_YELLOW = '\033[33m'
C_CYAN = '\033[36m'
C_GRAY = '\033[90m'
C_BOLD = '\033[1m'
C_END = '\033[0m'

# 文字順（ホームポジションから）
CHARS = list('はかとうきのにたいをるがしでてなっれらもすりこだまさめくあけどんえよつやそわちみせろばおじべずげほへびむごねぶぐぎひょづぼざふゃぞゆぜぬぱゅぴぽぷぺぁぇぢゑゐぉぃゎぅ')

# アンロック条件
UNLOCK_WPM = 30        # 最低WPM
UNLOCK_ACCURACY = 80   # 最低正答率(%)
ROUND_SIZE = 20        # 1ラウンドの問題数

# 単語
WORDS = [
    ("かう", "買う"), ("とう", "問う"), ("はく", "履く"), ("かく", "書く"), ("きく", "聞く"),
    ("かた", "型"), ("たか", "鷹"), ("うた", "歌"), ("きた", "北"), ("かき", "柿"),
    ("たき", "滝"), ("うき", "浮き"), ("はか", "墓"), ("の", "の"), ("に", "に"),
    ("たい", "鯛"), ("ない", "無い"), ("いた", "板"), ("たに", "谷"), ("はい", "灰"),
    ("はた", "旗"), ("はな", "花"), ("とい", "問い"), ("いと", "糸"), ("とる", "取る"),
    ("いる", "居る"), ("はる", "春"), ("なる", "成る"), ("のる", "乗る"), ("がい", "害"),
    ("しる", "知る"), ("しな", "品"), ("いし", "石"), ("にし", "西"), ("はし", "橋"),
    ("でる", "出る"), ("てる", "照る"), ("なに", "何"), ("かい", "貝"), ("かな", "仮名"),
    ("かに", "蟹"), ("いか", "烏賊"), ("しか", "鹿"), ("れい", "礼"), ("かれ", "彼"),
    ("これ", "これ"), ("それ", "それ"), ("から", "空"), ("なら", "奈良"), ("もの", "物"),
    ("もり", "森"), ("うし", "牛"), ("すな", "砂"), ("のり", "海苔"), ("とり", "鳥"),
    ("くり", "栗"), ("こい", "鯉"), ("ここ", "此処"), ("こと", "事"), ("この", "この"),
    ("だい", "台"), ("だれ", "誰"), ("まち", "町"), ("いま", "今"), ("くま", "熊"),
    ("さる", "猿"), ("さか", "坂"), ("あさ", "朝"), ("きり", "霧"), ("いき", "息"),
    ("すき", "好き"), ("あめ", "雨"), ("くち", "口"), ("くも", "雲"), ("くに", "国"),
    ("あい", "愛"), ("あか", "赤"), ("あき", "秋"), ("ある", "有る"), ("たけ", "竹"),
    ("さけ", "酒"), ("いけ", "池"), ("どこ", "何処"), ("まど", "窓"), ("えき", "駅"),
    ("かえる", "帰る"), ("まえ", "前"), ("うえ", "上"), ("よい", "良い"), ("よる", "夜"),
    ("つき", "月"), ("つく", "付く"), ("やま", "山"), ("そこ", "底"), ("わに", "鰐"),
    ("かわ", "川"), ("にわ", "庭"), ("ちり", "塵"), ("みち", "道"), ("みる", "見る"),
    ("うみ", "海"), ("ろく", "六"), ("しろ", "白"), ("ばか", "馬鹿"), ("おか", "丘"),
    ("おと", "音"), ("げた", "下駄"), ("ほし", "星"), ("へや", "部屋"), ("むし", "虫"),
    ("ねこ", "猫"), ("ねる", "寝る"), ("ぶた", "豚"), ("ひる", "昼"), ("ひと", "人"),
    ("ぼく", "僕"), ("ふく", "服"), ("ふね", "船"), ("ゆき", "雪"), ("ゆめ", "夢"),
    ("ぬの", "布"), ("ありがとう", "有難う"), ("おもしろい", "面白い"),
    ("たのしい", "楽しい"), ("ともだち", "友達"), ("せんせい", "先生"),
    ("にほん", "日本"), ("たべる", "食べる"), ("はなす", "話す"), ("わかる", "分かる"),
    ("はじめる", "始める"), ("おわる", "終わる"), ("わらう", "笑う"),
]

class Game:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE)
        self.init_db()
        self.unlocked = self.get_config('unlocked', 5)
        self.mastery = {c: self.get_mastery(c) for c in CHARS}
    
    def init_db(self):
        # 古いDBがあれば削除して作り直す
        try:
            self.conn.execute("SELECT val FROM config LIMIT 1")
        except:
            # 古いスキーマか新規 → リセット
            self.conn.executescript('''
                DROP TABLE IF EXISTS config;
                DROP TABLE IF EXISTS mastery;
                DROP TABLE IF EXISTS history;
            ''')
        
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, val INT);
            CREATE TABLE IF NOT EXISTS mastery(ch TEXT PRIMARY KEY, lv INT);
            CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, word TEXT, ok INT, ms INT, ts DATETIME DEFAULT CURRENT_TIMESTAMP);
        ''')
        self.conn.commit()
    
    def get_config(self, key, default):
        r = self.conn.execute("SELECT val FROM config WHERE key=?", (key,)).fetchone()
        return r[0] if r else default
    
    def set_config(self, key, val):
        self.conn.execute("REPLACE INTO config(key,val) VALUES(?,?)", (key, val))
        self.conn.commit()
    
    def get_mastery(self, ch):
        r = self.conn.execute("SELECT lv FROM mastery WHERE ch=?", (ch,)).fetchone()
        return r[0] if r else 0
    
    def set_mastery(self, ch, lv):
        self.conn.execute("REPLACE INTO mastery(ch,lv) VALUES(?,?)", (ch, lv))
        self.conn.commit()
        self.mastery[ch] = lv
    
    def add_history(self, word, ok, ms):
        self.conn.execute("INSERT INTO history(word,ok,ms) VALUES(?,?,?)", (word, ok, ms))
        self.conn.commit()
    
    def color(self, lv):
        if lv >= 80: return C_GREEN
        if lv >= 60: return C_YELLOW
        if lv >= 40: return C_CYAN
        if lv >= 1: return C_RED
        return C_GRAY
    
    def show_chars(self):
        print("\n  ", end="")
        for i, c in enumerate(CHARS):
            if i < self.unlocked:
                lv = self.mastery[c]
                print(f"{self.color(lv)}{c}{C_END}", end=" ")
            else:
                print(f"{C_GRAY}_{C_END}", end=" ")
            if (i + 1) % 20 == 0:
                print("\n  ", end="")
        print()
    
    def show_layout(self):
        avail = set(CHARS[:self.unlocked])
        def ch(c):
            if c in avail:
                return f"{self.color(self.mastery[c])}{c}{C_END}"
            return f"{C_GRAY}_{C_END}"
        
        print(f"\n  {C_CYAN}[通常]{C_END}                    {C_CYAN}[シフト]{C_END}")
        print(f"  {ch('そ')} {ch('こ')} {ch('し')} {ch('て')} {ch('ょ')}  {ch('つ')} {ch('ん')} {ch('い')} {ch('の')} {ch('り')} {ch('ち')}    {ch('ぁ')} {ch('ひ')} {ch('ほ')} {ch('ふ')} {ch('め')}  {ch('ぬ')} {ch('え')} {ch('み')} {ch('や')} {ch('ぇ')}")
        print(f"  {ch('は')} {ch('か')} * {ch('と')} {ch('た')}  {ch('く')} {ch('う')} * {ch('゛')} {ch('き')} {ch('れ')}    {ch('ぃ')} {ch('を')} {ch('ら')} {ch('あ')} {ch('よ')}  {ch('ま')} {ch('お')} {ch('も')} {ch('わ')} {ch('ゆ')}")
        print(f"  {ch('す')} {ch('け')} {ch('に')} {ch('な')} {ch('さ')}  {ch('っ')} {ch('る')} , . _    {ch('ぅ')} {ch('へ')} {ch('せ')} {ch('ゅ')} {ch('ゃ')}  {ch('む')} {ch('ろ')} {ch('ね')} - {ch('ぉ')}")
    
    def draw(self, ok, ng, q, total, wpm=0):
        os.system('clear')
        print(f"{C_CYAN}===== 月配列タイピング ====={C_END}")
        print(f"文字:{self.unlocked}/{len(CHARS)}  正解:{C_GREEN}{ok}{C_END} ミス:{C_RED}{ng}{C_END}  {q}/{total}  WPM:{C_YELLOW}{wpm}{C_END}")
        self.show_layout()
        print(f"{C_CYAN}----------------------------{C_END}")
        self.show_chars()
        print(f"{C_CYAN}----------------------------{C_END}")
    
    def available_words(self):
        avail = set(CHARS[:self.unlocked])
        return [(w, m) for w, m in WORDS if all(c in avail for c in w)]
    
    def update(self, word, ok):
        for c in word:
            lv = self.mastery.get(c, 0)
            lv = min(100, lv + 10) if ok else max(0, lv - 15)
            self.set_mastery(c, lv)
    
    def check_unlock(self, wpm, accuracy):
        if self.unlocked >= len(CHARS):
            return
        
        if wpm >= UNLOCK_WPM and accuracy >= UNLOCK_ACCURACY:
            self.unlocked += 1
            self.set_config('unlocked', self.unlocked)
            print(f"\n  {C_GREEN}* 新文字アンロック: {C_YELLOW}{CHARS[self.unlocked-1]}{C_END}")
            print(f"    (WPM:{wpm} >= {UNLOCK_WPM}, 正答率:{accuracy}% >= {UNLOCK_ACCURACY}%)")
            time.sleep(1.5)
            return True
        return False
    
    def play(self):
        words = self.available_words()
        if len(words) < 3:
            print("単語が足りません")
            input()
            return
        
        random.shuffle(words)
        n = min(ROUND_SIZE, len(words))
        ok = ng = 0
        total_chars = 0
        total_time = 0
        
        self.draw(0, 0, 0, n)
        input(f"\n  {C_GREEN}Enter で開始{C_END}")
        
        round_start = time.time()
        
        for i in range(n):
            word, mean = words[i]
            
            # 現在のWPM計算
            current_wpm = int(total_chars / (total_time / 60)) if total_time > 0 else 0
            
            self.draw(ok, ng, i+1, n, current_wpm)
            print(f"\n  {C_YELLOW}{C_BOLD}{word}{C_END} ({mean})\n")
            
            t0 = time.time()
            ans = input("  > ")
            elapsed = time.time() - t0
            ms = int(elapsed * 1000)
            
            if ans == word:
                ok += 1
                total_chars += len(word)
                total_time += elapsed
                self.update(word, True)
                self.add_history(word, 1, ms)
            else:
                ng += 1
                total_time += elapsed
                self.update(word, False)
                self.add_history(word, 0, ms)
                self.draw(ok, ng, i+1, n, current_wpm)
                print(f"\n  {C_RED}x{C_END} 正解:{C_YELLOW}{word}{C_END} 入力:{C_RED}{ans}{C_END}")
                input("  Enter...")
        
        # 最終結果
        final_wpm = int(total_chars / (total_time / 60)) if total_time > 0 else 0
        accuracy = ok * 100 // n if n > 0 else 0
        
        self.draw(ok, ng, n, n, final_wpm)
        print(f"\n  {C_BOLD}=== 結果 ==={C_END}")
        print(f"  正解: {C_GREEN}{ok}{C_END}/{n}")
        print(f"  正答率: {C_CYAN}{accuracy}%{C_END}", end="")
        if accuracy >= UNLOCK_ACCURACY:
            print(f" {C_GREEN}OK{C_END}")
        else:
            print(f" {C_RED}(要{UNLOCK_ACCURACY}%){C_END}")
        
        print(f"  WPM: {C_YELLOW}{final_wpm}{C_END}", end="")
        if final_wpm >= UNLOCK_WPM:
            print(f" {C_GREEN}OK{C_END}")
        else:
            print(f" {C_RED}(要{UNLOCK_WPM}){C_END}")
        
        # アンロック判定
        self.check_unlock(final_wpm, accuracy)
    
    def stats(self):
        r = self.conn.execute("SELECT COUNT(*), SUM(ok), SUM(ms) FROM history").fetchone()
        total, correct, total_ms = r[0], r[1] or 0, r[2] or 0
        
        # 正解した文字数を計算
        correct_rows = self.conn.execute("SELECT word FROM history WHERE ok=1").fetchall()
        total_chars = sum(len(row[0]) for row in correct_rows)
        
        print(f"\n  {C_BOLD}=== 統計 ==={C_END}")
        print(f"  総回答数: {total}")
        print(f"  正解: {C_GREEN}{correct}{C_END} / ミス: {C_RED}{total - correct}{C_END}")
        if total > 0:
            print(f"  正答率: {C_CYAN}{correct * 100 // total}%{C_END}")
        if total_ms > 0 and total_chars > 0:
            avg_wpm = int(total_chars / (total_ms / 1000 / 60))
            print(f"  平均WPM: {C_YELLOW}{avg_wpm}{C_END}")
        print(f"\n  アンロック条件: WPM >= {UNLOCK_WPM}, 正答率 >= {UNLOCK_ACCURACY}%")
    
    def reset(self):
        if input("  リセット? (y/n): ") == 'y':
            self.conn.executescript("DELETE FROM config; DELETE FROM mastery; DELETE FROM history;")
            self.unlocked = 5
            self.mastery = {c: 0 for c in CHARS}
            print(f"  {C_GREEN}リセット完了{C_END}")
    
    def run(self):
        while True:
            self.play()
            print(f"\n  {C_CYAN}1)続ける 2)統計 3)リセット 4)終了{C_END}")
            c = input("  > ")
            if c == '2': self.stats(); input()
            elif c == '3': self.reset()
            elif c == '4': print("お疲れ様!"); break

if __name__ == '__main__':
    Game().run()
