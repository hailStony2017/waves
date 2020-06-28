# coding: utf-8
import os
import re
import sys
import time
import json
import glob
import math
import random
import argparse
import requests
import datetime
from collections import defaultdict, OrderedDict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from lxml import etree
from tqdm import tqdm

import dash
import dash_core_components as dcc
import dash_html_components as html

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server

def max_min_nomralization(x, max, min):
    if max != min:
        return (x - min) * 100.0 / (max - min)
    else:
        return 100.0

class WeiboTalent:
    # 基于 m.weibo.cn 抓取少量数据，无需登陆验证
    url_template = "https://m.weibo.cn/api/container/getIndex?type=wb&queryVal={}&containerid=100103type=2%26q%3D{}&page={}"

    def __init__(self, user_name, user_id, filter=0, **kwargs):
        self.user_name = user_name
        self.user_id = user_id
        self.weibo = []
        self.got_count = 0
        self.related_posts = []
        self.filter = filter

        for k in kwargs:
            setattr(self, k, kwargs.get(k))

    def get_json(self, params):
        """获取网页中json数据"""
        url = 'https://m.weibo.cn/api/container/getIndex?'
        r = requests.get(url, params=params)
        return r.json()

    def get_weibo_json(self, page):
        """获取网页中微博json数据"""
        params = {'containerid': '107603' + str(self.user_id), 'page': page}
        js = self.get_json(params)
        return js

    def get_user_info(self):
        """获取用户信息"""
        params = {'containerid': '100505' + str(self.user_id)}
        js = self.get_json(params)
        if js['ok']:
            info = js['data']['userInfo']
            if info.get('toolbar_menus'):
                del info['toolbar_menus']
            user_info = self.standardize_info(info)
            self.user = user_info
            self.followers_count = user_info['followers_count']
            self.statuses_count = user_info['statuses_count']

    def print_user_info(self):
        """打印用户信息"""
        print('+' * 100)
        print(u'用户信息')
        print(u'用户id：%d' % self.user['id'])
        print(u'用户昵称：%s' % self.user['screen_name'])
        gender = u'女' if self.user['gender'] == 'f' else u'男'
        print(u'性别：%s' % gender)
        print(u'微博数：%d' % self.user['statuses_count'])
        print(u'粉丝数：%d' % self.user['followers_count'])
        print(u'关注数：%d' % self.user['follow_count'])
        if self.user.get('verified_reason'):
            print(self.user['verified_reason'])
        print(self.user['description'])
        print('+' * 100)

    def print_one_weibo(self, weibo):
        """打印一条微博"""
        print(u'微博id：%s' % weibo['id'])
        print(u'微博正文：%s' % weibo['text'])
        print(u'发布时间：%s' % weibo['created_at'])
        print(u'发布工具：%s' % weibo['source'])
        print(u'点赞数：%d' % weibo['attitudes_count'])
        print(u'评论数：%d' % weibo['comments_count'])
        print(u'转发数：%d' % weibo['reposts_count'])

    def print_weibo(self, weibo):
        """打印微博，若为转发微博，会同时打印原创和转发部分"""
        if weibo.get('retweet'):
            print('*' * 100)
            print(u'转发部分：')
            self.print_one_weibo(weibo['retweet'])
            print('*' * 100)
            print(u'原创部分：')
        self.print_one_weibo(weibo)
        print('-' * 120)

    def string_to_int(self, string):
        """字符串转换为整数"""
        if isinstance(string, int):
            return string
        elif string.endswith(u'万+'):
            string = int(string[:-2] + '0000')
        elif string.endswith(u'万'):
            string = int(string[:-1] + '0000')
        return int(string)

    def get_long_weibo(self, id):
        """获取长微博"""
        url = 'https://m.weibo.cn/detail/%s' % id
        html = requests.get(url).text
        html = html[html.find('"status":'):]
        html = html[:html.rfind('"hotScheme"')]
        html = html[:html.rfind(',')]
        html = '{' + html + '}'
        js = json.loads(html, strict=False)
        weibo_info = js['status']
        weibo = self.parse_weibo(weibo_info)
        return weibo

    def parse_weibo(self, weibo_info):
        weibo = OrderedDict()
        weibo['user_id'] = weibo_info['user']['id']
        weibo['screen_name'] = weibo_info['user']['screen_name']
        weibo['id'] = int(weibo_info['id'])
        text_body = weibo_info['text']
        selector = etree.HTML(text_body)
        weibo['text'] = etree.HTML(text_body).xpath('string(.)')
        weibo['created_at'] = weibo_info['created_at']
        weibo['source'] = weibo_info['source']
        weibo['attitudes_count'] = self.string_to_int(
            weibo_info['attitudes_count'])
        weibo['comments_count'] = self.string_to_int(
            weibo_info['comments_count'])
        weibo['reposts_count'] = self.string_to_int(
            weibo_info['reposts_count'])
        return self.standardize_info(weibo)

    def get_one_weibo(self, info):
        """获取一条微博的全部信息"""
        weibo_info = info['mblog']
        weibo_id = weibo_info['id']
        retweeted_status = weibo_info.get('retweeted_status')
        is_long = weibo_info['isLongText']
        if retweeted_status:  # 转发
            retweet_id = retweeted_status['id']
            is_long_retweet = retweeted_status['isLongText']
            if is_long:
                weibo = self.get_long_weibo(weibo_id)
            else:
                weibo = self.parse_weibo(weibo_info)
            if is_long_retweet:
                retweet = self.get_long_weibo(retweet_id)
            else:
                retweet = self.parse_weibo(retweeted_status)
            retweet['created_at'] = self.standardize_date(
                retweeted_status['created_at'])
            weibo['retweet'] = retweet
        else:  # 原创
            if is_long:
                weibo = self.get_long_weibo(weibo_id)
            else:
                weibo = self.parse_weibo(weibo_info)
        weibo['created_at'] = self.standardize_date(weibo_info['created_at'])
        return weibo

    def get_one_page(self, page):
        """获取一页的全部微博"""
        try:
            js = self.get_weibo_json(page)
            if js['ok']:
                weibos = js['data']['cards']
                for w in weibos:
                    if w['card_type'] == 9:
                        wb = self.get_one_weibo(w)
                        if (not self.filter) or ('retweet' not in wb.keys()):
                            self.weibo.append(wb)
                            self.got_count = self.got_count + 1
                            # self.print_weibo(wb)
        except Exception as e:
            print("Error: ", e)

    def get_pages(self, page_count):
        """获取全部微博"""
        self.get_user_info()
        self.print_user_info()
        for page in tqdm(range(1, page_count + 1), desc=u"进度"):
            print(u'第%d页' % page)
            self.get_one_page(page)

            # 通过加入随机等待避免被限制。爬虫速度过快容易被系统限制(一段时间后限
            # 制会自动解除)，加入随机等待模拟人的操作，可降低被系统限制的风险
            time.sleep(random.randint(2, 4))

        print(u'微博爬取完成，共爬取%d条微博' % self.got_count)

    @staticmethod
    def standardize_info(weibo):
        """标准化信息，去除乱码"""
        for k, v in weibo.items():
            if 'int' not in str(type(v)) and 'long' not in str(
                    type(v)) and 'bool' not in str(type(v)):
                weibo[k] = v.replace(u"\u200b", "").encode(
                    sys.stdout.encoding, "ignore").decode(sys.stdout.encoding)
        return weibo

    @staticmethod
    def standardize_date(created_at):
        """标准化微博发布时间"""
        if u"刚刚" in created_at:
            created_at = datetime.datetime.now().strftime("%Y-%m-%d")
        elif u"分钟" in created_at:
            minute = created_at[:created_at.find(u"分钟")]
            minute = datetime.timedelta(minutes=int(minute))
            created_at = (datetime.datetime.now() - minute).strftime("%Y-%m-%d")
        elif u"小时" in created_at:
            hour = created_at[:created_at.find(u"小时")]
            hour = datetime.timedelta(hours=int(hour))
            created_at = (datetime.datetime.now() - hour).strftime("%Y-%m-%d")
        elif u"昨天" in created_at:
            day = datetime.timedelta(days=1)
            created_at = (datetime.datetime.now() - day).strftime("%Y-%m-%d")
        elif created_at.count('-') == 1:
            year = datetime.datetime.now().strftime("%Y")
            created_at = year + "-" + created_at
        return created_at
    @staticmethod
    def clean_text(text):
        """清除文本中的标签等信息"""
        dr = re.compile(r'(<)[^>]+>', re.S)
        dd = dr.sub('', text)
        dr = re.compile(r'#[^#]+#', re.S)
        dd = dr.sub('', dd)
        dr = re.compile(r'@[^ ]+ ', re.S)
        dd = dr.sub('', dd)
        return dd.strip()

    def fetch_data(self, page_id):
        """抓取关键词某一页的数据"""
        resp = requests.get(self.url_template.format(self.user_name, self.user_name, page_id))

        if resp.status_code is not 200:
            print(f"Error response code: {resp.status_code}")
            return []

        time.sleep(3)
        card_group = json.loads(resp.text)['data']['cards'][0]['card_group']
        print('url：', resp.url, ' --- 条数:', len(card_group))

        mblogs = []  # 保存处理过的微博
        for card in card_group:
            mblog = card['mblog']

            blog = {'mid': mblog['id'],  # 微博id
                    'text': self.clean_text(mblog['text']),  # 文本
                    'userid': str(mblog['user']['id']),  # 用户id
                    'username': mblog['user']['screen_name'],  # 用户名
                    'reposts_count': mblog['reposts_count'],  # 转发
                    'comments_count': mblog['comments_count'],  # 评论
                    'attitudes_count': mblog['attitudes_count'],  # 点赞
                    'created_at': mblog['created_at']   # 发布时间
                    }
            mblogs.append(blog)
        return mblogs

    def get_related_posts(self, page_num):
        """抓取关键词多页的数据"""
        mblogs = []
        for page_id in range(1 + page_num + 1):
            try:
                page_data = self.fetch_data(page_id)
                mblogs.extend(page_data)
            except Exception as e:
                print(e)

        # print("Total weibo：", len(mblogs))

        self.related_posts = mblogs

    @property
    def related_retweets_count(self):
        return sum(p['reposts_count'] for p in self.related_posts if '-' not in p['created_at']) + len(self.related_posts)

    @property
    def related_comments_count(self):
        return sum(p['comments_count'] for p in self.related_posts if '-' not in p['created_at'])

    @property
    def related_attitudes_count(self):
        return sum(p['attitudes_count'] for p in self.related_posts if '-' not in p['created_at'])

    @property
    def reposts_count(self):
        return sum(p['reposts_count'] for p in self.weibo)

    @property
    def comments_count(self):
        return sum(p['comments_count'] for p in self.weibo)

    @property
    def attitudes_count(self):
        return sum(p['attitudes_count'] for p in self.weibo)

    @property
    def cogn_score(self):
        """根据艺人的微博粉丝数计算的分数"""
        return self.followers_count / math.log(self.statuses_count + 1)

    @property
    def attn_score(self):
        """根据艺人相关微博的信息计算的分数"""
        # return self.related_retweets_count * 1 + \
        #        self.related_comments_count * 1 + \
        #        self.related_attitudes_count * 1
        return (self.reposts_count * 1 + \
               self.comments_count * 1 + \
               self.attitudes_count * 1) / self.got_count
    @property
    def scores(self):
        return {
            "user_name": self.user_name,
            "attn_score": self.attn_score,
            "cogn_score": self.cogn_score,
            "norm_attn_score": self.norm_attn_score,
            "norm_cogn_score": self.norm_cogn_score
        }

    def __str__(self):
        talent = {
            "user_name": self.user_name,
            "user_id": self.user_id,
            "followers_count": self.followers_count,
            "related_posts": self.related_posts
        }
        return json.dumps(talent, ensure_ascii=False)

    @property
    def keyinfo(self):
        talent = {
            "user_name": self.user_name,
            "user_id": self.user_id,
            "followers_count": self.followers_count,
            "statuses_count": self.statuses_count,
            "related_posts": self.related_posts,
            "weibo": self.weibo,
            "got_count": self.got_count
        }
        return talent



now = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
input = "wave.txt"

output_file = "outputs/"+ input.split(".")[0] + f"_score_{now}.json"

list_of_files = glob.glob("outputs/"+input.split(".")[0]+"*")
latest_file = max(list_of_files, key=os.path.getctime)

print(f"Loading latest output file {latest_file}")
with open(latest_file, 'r', encoding="utf8") as f:
    all_talents_str = f.read()

all_talents_str = json.loads(all_talents_str)
all_talents = [WeiboTalent(t['user_name'],
                           t['user_id'],
                           followers_count=t['followers_count'],
                           statuses_count=t['statuses_count'],
                           related_posts=t['related_posts'],
                           got_count=t['got_count'],
                           weibo=t['weibo'])
               for t in all_talents_str]

max_cogn_score = max(t.cogn_score for t in all_talents) * 1.1
min_cogn_score = min(t.cogn_score for t in all_talents) * 0.9
# min_cogn_score = 1000000
max_attn_score = max(t.attn_score for t in all_talents) * 1.1
# max_attn_score = 20000
min_attn_score = min(t.attn_score for t in all_talents) * 0.9
# min_attn_score = 1
for t in all_talents:
    t.norm_cogn_score = max_min_nomralization(t.cogn_score, max_cogn_score, min_cogn_score)
    t.norm_attn_score = max_min_nomralization(t.attn_score, max_attn_score, min_attn_score)

talent_pd = pd.DataFrame.from_records([t.scores for t in all_talents])
fig = px.scatter(talent_pd,
                 x="norm_cogn_score",
                 y="norm_attn_score",
                 text='user_name',
                 size="norm_cogn_score",
                 color='norm_attn_score',
                 log_x=True,
                 log_y=True)
fig.update_layout(
    title=go.layout.Title(
        text="乘风破浪的姐姐微博势力榜"
    ),
    xaxis=go.layout.XAxis(
        title=go.layout.xaxis.Title(
            text="认知度"
        )
    ),
    yaxis=go.layout.YAxis(
        title=go.layout.yaxis.Title(
            text="关心度"
        )
    )
    # font_size=11,
    # width=1500,
    # height=500

)
# fig.write_html("templates/index.html")

app.layout = html.Div([

    dcc.Graph(figure=fig)
])
app.title = "乘风破浪的姐姐微博势力榜"

if __name__ == "__main__":
    app.run_server()

