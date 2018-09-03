# _*_ coding:utf-8 _*_

import requests
from requests.auth import HTTPBasicAuth
import json
import os
import operator
import smtplib
from email.mime.text import MIMEText
import logging
import re

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S',
                    filename='myapp.log',
                    filemode='a'
                    )
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)


class ProjectacrnPullRequest(object):

    def __init__(self, username, userpwd):
        self.base_url = 'https://api.github.com/repos/projectacrn/acrn-hypervisor/pulls'
        self.url = ''
        self.s = requests.Session()
        self.s.auth = HTTPBasicAuth(username, userpwd)

    def send_email(self, subject, content, mail=[]):
        # Send a reminder email
        # 发送邮件
        sender = 'Integration_auto_merge@intel.com'  # 邮件发送人可以为一个虚拟的邮箱（需要加后缀@...com）
        receivers = ['weix.hao@intel.com', 'jinxiax.li@intel.com', 'wenling.zhang@intel.com',
                     'nanlin.xie@intel.com'] + mail
        msg = MIMEText(content, 'plain', 'utf-8')

        msg['Subject'] = subject
        msg['From'] = sender
        msg['TO'] = ','.join(receivers)
        try:
            s = smtplib.SMTP('smtp.intel.com')
            s.sendmail(sender, receivers, msg.as_string())
            logging.info('send suess')
        except smtplib.SMTPException as err:
            logging.info('Failed to send mail\n %s' % err)

    def acrn_url_info(self, url):
        # request data
        response = self.s.get(url)
        return json.loads(response.text)

    def post_comments(self, url):
        # Post Merge Comments

        body = "Ready to merge"
        response = self.s.post(url, json={'body': body})
        return response.status_code

    def merge_put_request_method(self, merge_url, head):
        # Rebase Merge

        response = self.s.put(merge_url, json={"sha": head, "merge_method": "rebase"})
        return response.text

    def read_file(self):
        # 读取保存本地的字典文件（以后可以修改为读取数据库）
        try:
            with open('num_dict.json', 'r') as f:
                merge_num = f.read()
            return eval(merge_num)
        except FileNotFoundError as e:
            return {}

    def write_file(self, num_list):
        # 保存到本地字典文件 （以后可以保存到数据库）
        with open('num_dict.json', 'w') as f:
            f.write(str(num_list))

    def determine_doc(self, num):
        # 检查commit的文件是否为doc文档文件
        # 需求：文件不全为doc返回True
        url = 'https://api.github.com/repos/projectacrn/acrn-hypervisor/pulls/%s/files' % num
        try:
            file_list = self.acrn_url_info(url)
            for file in file_list:
                file_type = file['filename'].split('/', 1)[0]
                if file_type != 'doc':
                    return True
        except Exception as e:
            logging.info('%s' % e)
        else:
            return False

    def TrackenOn(self, num, commit_url, html_url):
        # 检查是否TrackOn
        try:
            message = self.acrn_url_info(commit_url)[0]['commit']['message']
            me_list = re.findall(r'Tracked-On: #(\d+)', message)
            mail = re.findall(r'Signed-off-by:.*?<(.*?@.*?)>', message)
        except Exception as e:
            logging.error('commit链接获取错误 %s' % e)
            return False
        if not me_list:
            # 没有TrackOn信息
            if not mail:
                # commit中没有邮件联系人
                logging.info('%s 未找到mail 邮件发给谁' % num)
                subject = 'Waring: NO Tracked-On for PR %d' % num
                content = 'No contact found for PR %d, No Tracken-On information, link: %s' % (num, html_url)
                mail.append('minxia.wang@intel.com')
                self.send_email(subject, content)
            else:
                # 没有TrackOn但有联系人发送邮件
                logging.info('找到mail发邮件')
                subject = 'Warning: No Tracken-On information in %d PR' % num
                content = 'Warning: No "Tracked-On" info in %s PATH: %s please add it' % (num, html_url)
                mail.append('minxia.wang@intel.com')
                self.send_email(subject, content, mail)
            return False
        issues_num = int(me_list[0])
        issues_url = "https://api.github.com/repos/projectacrn/acrn-hypervisor/issues/%d/comments" % issues_num
        try:
            # 有TranckOn查看相关链接
            ext_list = []
            body = self.acrn_url_info(issues_url)
            for message in body:
                try:
                    ID = message['body']
                except Exception as e:
                    continue
                ext_list = re.findall(r'\[External_System_ID\]', ID)
            if not ext_list:
                logging.info('%s未找到ID发邮件 需要发送给5个人' % num)
                subject = 'Waring: No External_System-ID'
                content = "PR%s`s issues %s External_System_ID was not found in the issues of PR link: %s" % (num,
                                                                                                              issues_num,
                                                                                                              html_url)
                self.send_email(subject, content)
                return False
        except Exception as e:
            logging.error('issuers链接错误发邮件 需要发送给5个人 %s' % e)
            subject = 'Git Issue link error'
            content = 'Git Issue link error %s, maybe Tracken-On infomation error' % issues_url
            self.send_email(subject, content)
            return False
        else:
            logging.info('check-on OK')
            return True

    def projectcarn_merge_rebase(self):
        # Parse the json data and execute the method
        read_num_dict = self.read_file()
        merge_num_dict = {}
        trackon_dict = {}
        pulls_json = self.acrn_url_info(self.base_url)
        # merge_url = pulls_json[0]['base']['repo']['merges_url']
        for pull_json in pulls_json:
            head = pull_json['head']['sha']
            base = pull_json['base']['ref']
            commits_url = pull_json['commits_url']
            num_url = pull_json['url']
            num = pull_json['number']
            comment_url = pull_json['comments_url']
            statuses_url = pull_json['statuses_url']
            per_mail_url = pull_json['head']['repo']['url']
            review_url = pull_json['url'] + '/reviews'
            html_url = pull_json['html_url']
            if self.determine_doc(num):
                if self.TrackenOn(num, commits_url, html_url):
                    trackon_dict[num] = num_url
                rebaseable = self.acrn_url_info(num_url)['rebaseable']
                if not rebaseable:
                    # 发送邮件： 代码没有合并的
                    rebase_list = []
                    master_data = self.acrn_url_info(per_mail_url+'/branches/master')
                    email = master_data['commit']['commit']['author']['email']
                    rebase_list.append(email)
                    subject = "Warning: Has conflicts,please resolve"
                    content = "Warning: Has conflicts, need resolved,%d PATH:%s " % (num, num_url)
                    self.send_email(subject, content, rebase_list)
                    continue
                review_json = self.acrn_url_info(review_url)
                for review in review_json:
                    user = review["user"]["login"]
                    if review.get('state') == "APPROVED" and (user == "anthonyzxu" or user == "dongyaozu"):
                        check_json = self.acrn_url_info(statuses_url)
                        if check_json[0]['state'] == 'success':
                            merge_num_dict[num] = [0, comment_url, num_url]

        merge_num_list = sorted(merge_num_dict.keys())
        read_num_list = sorted(read_num_dict.keys())
        ok_merge = list(set(merge_num_list) & set(sorted(trackon_dict.keys())))
        # ok_no_trackon = list(set(merge_num_list) - set(sorted(trackon_dict.keys())))
        ok_merge_dict = {x: y[2] for x, y in merge_num_dict.items() if x in ok_merge}
        # ok_no_trackon_dict = {x: y[2] for x, y in merge_num_dict.items() if x in ok_no_trackon}
        logging.info('merge_num_list %s' % merge_num_list)
        logging.info('read_num_list %s' % read_num_list)
        if not operator.eq(read_num_list, merge_num_list):
            # 使用operator判断两个列表是否相同
            logging.info("可以rebase编号：%s" % merge_num_list)
            # 发送邮件：可以merge的PR列表
            subject = 'Need merge PRs'
            content = 'PR can merge list:\n %s' % (
                json.dumps(ok_merge_dict))
            self.send_email(subject, content)
            for num, me_list in merge_num_dict.items():
                if num in read_num_list:
                    merge_num_dict[num][0] = 1
                    me_list[0] = 1
                if me_list[0] == 0:
                    status_code = self.post_comments(me_list[1])
                    merge_num_dict[num][0] = 1
                    body = "修改成功" if status_code == 201 else "修改失败"
                    logging.info(body)
            self.write_file(merge_num_dict)


if __name__ == '__main__':
    projectacrn_pullrequest = ProjectacrnPullRequest('hw121298@163.com', 'hw!QAZ2wsx')
    projectacrn_pullrequest.projectcarn_merge_rebase()
