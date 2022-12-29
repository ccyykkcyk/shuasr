# -*- coding: UTF-8 -*-
import json
import base64
import re
import threading
import time
import traceback
import requests
import rsa
import yaml
import datetime
import os
import random
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

abs_path = os.path.split(os.path.realpath(__file__))[0]

GRAB_LOGS = {'success': [], 'fail': []}
READ_MSG_RESULTS = []


def getTime():
    t = datetime.datetime.utcnow()
    t += datetime.timedelta(hours=8)
    return t


# 2021.04.17 更新密码加密
def encryptPass(password):
    key_str = '''-----BEGIN PUBLIC KEY-----
    MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDl/aCgRl9f/4ON9MewoVnV58OL
    OU2ALBi2FKc5yIsfSpivKxe7A6FitJjHva3WpM7gvVOinMehp6if2UNIkbaN+plW
    f5IwqEVxsNZpeixc4GsbY9dXEk3WtRjwGSyDLySzEESH/kpJVoxO7ijRYqU+2oSR
    wTBNePOk1H+LRQokgQIDAQAB
    -----END PUBLIC KEY-----'''
    pub_key = rsa.PublicKey.load_pkcs1_openssl_pem(key_str.encode('utf-8'))
    crypto = base64.b64encode(rsa.encrypt(password.encode('utf-8'), pub_key)).decode()
    return crypto


def login(username, password, try_once=False):
    default_url = "https://selfreport.shu.edu.cn/Default.aspx"
    form_data = {
        'username': username,
        'password': encryptPass(password),
        'login_submit': None,
    }
    login_times = 0
    while True:
        try:
            session = requests.Session()
            session.headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.36 (' \
                                            'KHTML, like Gecko) Chrome/34.0.1847.131 Safari/537.36'
            session.trust_env = False
            session.keep_alive = False
            retry = Retry(connect=5, backoff_factor=10)
            adapter = HTTPAdapter(max_retries=retry)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            sso = session.get(url=default_url)
            post_index = session.post(url=sso.url, data=form_data, allow_redirects=False)
            index = session.get(url='https://newsso.shu.edu.cn/oauth/authorize?client_id=WUHWfrntnWYHZfzQ5QvXUCVy'
                                    '&response_type=code&scope=1&redirect_uri=https%3A%2F%2Fselfreport.shu.edu.cn'
                                    '%2FLoginSSO.aspx%3FReturnUrl%3D%252fDefault.aspx&state=')
            login_times += 1
            notice_url = 'https://selfreport.shu.edu.cn/DayReportNotice.aspx'
            view_msg_url = 'https://selfreport.shu.edu.cn/ViewMessage.aspx'
            if index.url == default_url and index.status_code == 200:
                if '需要更新' in index.text:
                    cleanIndex(session, index.text, 'cancel_archive_dialog', default_url, default_url)
                return session
            elif index.url.startswith(view_msg_url):
                view_times = 0
                while view_times < 10:
                    index = session.get(url=default_url)
                    view_times += 1
                    if index.url == default_url:
                        print('已阅读%s条强制消息' % view_times)
                        return session
            elif index.url == notice_url:
                if cleanIndex(session, index.text, 'read_notice', notice_url, default_url):
                    return session
            elif 'message.login.passwordError' in post_index.text:
                if login_times > 2:
                    print('用户密码错误')
                    return False
            else:
                print('出现未知错误，历史记录调试信息：')
                print([u.url for u in index.history] + [index.url])
        except Exception as e:
            print(e)
            traceback.print_exc()

        del session

        if try_once:
            return False
        if login_times > 3:
            print('尝试登录次数过多')
            return False
        time.sleep(20)


def cleanIndex(session, html, target, target_url, index_url):
    view_state = re.search(r'id="__VIEWSTATE" value="(.*?)" /', html).group(1)
    view_state_generator = re.search(r'id="__VIEWSTATEGENERATOR" value="(.*?)" /', html).group(1)
    form_data = {
        '__VIEWSTATE': view_state,
        '__VIEWSTATEGENERATOR': view_state_generator,
    }
    if target == 'read_notice':
        form_data.update({
            '__EVENTTARGET': 'p1$ctl01$btnSubmit',
            '__EVENTARGUMENT': '',
            'F_TARGET': 'p1_ctl01_btnSubmit',
            'p1_ctl00_Collapsed': 'false',
            'p1_Collapsed': 'false',
            'F_STATE': 'eyJwMV9jdGwwMCI6eyJJRnJhbWVBdHRyaWJ1dGVzIjp7fX0sInAxIjp7IklGcmFtZUF0dHJpYnV0ZXMiOnt9fX0=',
        })
    elif target == 'cancel_archive_dialog':
        form_data.update({
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': 'EArchiveCancel',
            'frmConfirm_ContentPanel1_Collapsed': 'false',
            'frmConfirm_Collapsed': 'false',
            'frmConfirm_Hidden': 'true',
            'F_STATE': 'eyJmcm1Db25maXJtX0NvbnRlbnRQYW5lbDEiOnsiSUZyYW1lQXR0cmlidXRlF_STATEcyI6e319LCJmcm1Db25maXJtIjp'
                       '7IklGcmFtZUF0dHJpYnV0ZXMiOnt9fX0=',
        })
    else:
        return False
    index = session.post(url=target_url, data=form_data)
    if index.url == index_url:
        return True


def generateFState(json_file, post_day=None, province=None, city=None, county=None, address=None, in_shanghai=None,
                   in_school=None, in_home=None, ans=None, campus=None, entry_campus=None, street=None, in_out=None,
                   risk=None, out_province=None, back_sh=None):
    with open(json_file, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    json_data['p1_BaoSRQ']['Text'] = post_day

    json_data['p1_JinChuSQ']['SelectedValue'] = in_out
    json_data['p1_GaoZDFXLJS']['SelectedValue'] = risk

    json_data['p1_ddlSheng']['SelectedValueArray'][0] = province
    json_data['p1_ddlSheng']['F_Items'][0][0] = province
    json_data['p1_ddlSheng']['F_Items'][0][1] = province

    json_data['p1_ddlShi']['SelectedValueArray'][0] = city
    json_data['p1_ddlShi']['F_Items'][0][0] = city
    json_data['p1_ddlShi']['F_Items'][0][1] = city

    json_data['p1_ddlXian']['SelectedValueArray'][0] = county
    json_data['p1_ddlXian']['F_Items'][0][0] = county
    json_data['p1_ddlXian']['F_Items'][0][1] = county

    json_data['p1_ddlJieDao']['F_Items'][0] = [street, street, 1, '', '']
    json_data['p1_ddlJieDao']['SelectedValueArray'][0] = street

    json_data['p1_XiangXDZ']['Text'] = address

    json_data['p1_P_GuoNei_ShiFSH']['SelectedValue'] = in_shanghai
    json_data['p1_P_GuoNei_ShiFZX']['SelectedValue'] = in_school
    json_data['p1_P_GuoNei_XiaoQu']['SelectedValue'] = campus
    json_data['p1_P_GuoNei_JinXXQ']['SelectedValueArray'] = entry_campus
    json_data['p1_ShiFZJ']['SelectedValue'] = in_home

    json_data['p1_CengFWSS']['SelectedValue'] = out_province
    json_data['p1_DiHRQ']['Text'] = back_sh
    json_data['p1_DiHRQ']['Required'] = True if not not back_sh else False

    json_data['p1_pnlDangSZS_DangSZS']['SelectedValueArray'] = ans

    fstate = base64.b64encode(json.dumps(json_data).encode("utf-8")).decode("utf-8")
    return fstate


def html2JsLine(html):
    js = re.search(r'F\.load.*]>', html).group(0)
    split = js.split(';var ')
    return split


def jsLine2Json(js):
    return json.loads(js[js.find('=') + 1:])


def getLatestInfo(session):
    history_url = 'https://selfreport.shu.edu.cn/ReportHistory.aspx'
    index = session.get(url=history_url).text
    js_str = re.search('f2_state=(.*?);', index).group(1)
    items = json.loads(js_str)['F_Items']
    info_url = 'https://selfreport.shu.edu.cn'
    for i in items:
        if '已按时填报' in i[1] or '已补报' in i[1]:
            info_url += i[4]
            break

    info_html = session.get(url=info_url).text
    info_line = html2JsLine(info_html)

    in_shanghai = '在上海（校内）'
    in_school = '是'
    campus = '宝山'
    entry_campus = ['宝山']
    province = '上海'
    city = '上海'
    county = '宝山区'
    street = '大场镇'
    address = '上海大学宝山校区'
    in_home = '否'
    # 假期期间默认设置为不需要申请
    in_out = "0"
    # 高中低风险
    risk = '无'
    # 曾赴外省市
    out_province = '否'
    # 抵沪日期
    back_sh = ''
    for i, h in enumerate(info_line):
        if 'ShiFSH' in h:
            in_shanghai = jsLine2Json(info_line[i - 1])['Text']
        elif 'ShiFZX' in h:
            in_school = jsLine2Json(info_line[i - 1])['SelectedValue']
        elif 'ddlSheng' in h:
            province = jsLine2Json(info_line[i - 1])['SelectedValueArray'][0]
        elif 'ddlShi' in h:
            city = jsLine2Json(info_line[i - 1])['SelectedValueArray'][0]
        elif 'ddlXian' in h:
            county = jsLine2Json(info_line[i - 1])['SelectedValueArray']
            if not county:
                county = ''
            else:
                county = county[0]
        elif 'ddlJieDao' in h:
            street = jsLine2Json(info_line[i - 1])['SelectedValueArray']
            if not street:
                street = -1
            else:
                street = street[0]
        elif 'XiangXDZ' in h:
            address = jsLine2Json(info_line[i - 1])['Text']
        elif 'ShiFZJ' in h:
            in_home = jsLine2Json(info_line[i - 1])['SelectedValue']
        elif 'GaoZDFXLJS' in h:
            try:
                risk = jsLine2Json(info_line[i - 1])['Text']
            except (json.JSONDecodeError, KeyError):
                continue
            if '低' in risk:
                risk = '低'
            elif '中' in risk:
                risk = '中'
            elif '高' in risk:
                risk = '高'
            else:
                risk = '无'
        elif 'CengFWSS' in h:
            try:
                out_province = jsLine2Json(info_line[i - 1])['Text']
            except (json.JSONDecodeError, KeyError):
                out_province = '否'
                continue
        elif 'DiHRQ' in h:
            try:
                back_sh = jsLine2Json(info_line[i - 1])['Text']
            except (json.JSONDecodeError, KeyError):
                back_sh = ''
                continue

    if '（校内）' in in_shanghai and in_school == '是':
        for i, h in enumerate(info_line):
            if 'XiaoQu' in h:
                try:
                    campus = jsLine2Json(info_line[i - 1])['Text']
                except (KeyError, json.JSONDecodeError):
                    if county == '静安区':
                        campus = '延长'
                    elif county == '嘉定区':
                        campus = '嘉定'
                    else:
                        campus = '宝山'
                break

        for i, h in enumerate(info_line):
            if 'JinXXQ' in h:
                try:
                    entry_campus = jsLine2Json(info_line[i - 1])['Text'].split(';')
                except (KeyError, json.JSONDecodeError):
                    entry_campus = [campus]
                break

    if province == '上海' and street == '-1':
        if county == '静安区':
            street = '大宁路街道'
        elif county == '嘉定区':
            street = '嘉定镇街道'
        elif county == '宝山区':
            street = '大场镇'

    report_url = 'https://selfreport.shu.edu.cn/DayReport.aspx'
    report_html = session.get(url=report_url).text

    _ = re.search(r'ok:\'F\.f_disable\(\\\'(.*?)\\\'\);__doPostBack\(\\\'(.*?)\\\',\\\'\\\'\);\',', report_html)
    f_target = _.group(1)
    even_target = _.group(2)
    view_state = re.search(r'id="__VIEWSTATE" value="(.*?)" /', report_html).group(1)
    view_state_generator = re.search(r'id="__VIEWSTATEGENERATOR" value="(.*?)" /', report_html).group(1)

    ans = ['A']

    info = dict(
        vs=view_state, vsg=view_state_generator, f_target=f_target, even_target=even_target, in_out=in_out,
        in_shanghai=in_shanghai, entry_campus=entry_campus, in_school=in_school, campus=campus, in_home=in_home,
        province=province, city=city, county=county, address=address, street=street, risk=risk, back_sh=back_sh,
        ans=ans, out_province=out_province,
    )

    return info


def getReportForm(post_day, info):
    view_state = info['vs']
    view_state_generator = info['vsg']
    in_out = info['in_out']
    province = info['province']
    city = info['city']
    county = info['county']
    street = info['street']
    address = info['address']
    in_shanghai = info['in_shanghai']
    entry_campus = info['entry_campus']
    in_school = info['in_school']
    campus = info['campus']
    in_home = info['in_home']
    risk = info['risk']
    out_province = info['out_province']
    back_sh = info['back_sh']
    f_target = info['f_target']
    even_target = info['even_target']
    ans = info['ans']

    # temperature = str(round(random.uniform(36.3, 36.7), 1))

    f_state = generateFState(json_file=abs_path + '/once.json', post_day=post_day, province=province, city=city,
                             county=county, address=address, in_shanghai=in_shanghai, in_school=in_school,
                             in_home=in_home, ans=ans, campus=campus, entry_campus=entry_campus, street=street,
                             in_out=in_out, risk=risk, out_province=out_province, back_sh=back_sh)

    report_form = {
        '__EVENTTARGET': even_target,
        '__EVENTARGUMENT': '',
        '__VIEWSTATE': view_state,
        '__VIEWSTATEGENERATOR': view_state_generator,
        'p1$ChengNuo': 'p1_ChengNuo',
        'p1$pnlDangSZS$DangSZS': ans,
        'p1$P_QueZXX$CengQZ': '否',
        'p1$BaoSRQ': post_day,
        'p1$DangQSTZK': '良好',
        'p1$TiWen': '',
        'p1$JiuYe_ShouJHM': '',
        'p1$JiuYe_Email': '',
        'p1$JiuYe_Wechat': '',
        'p1$QiuZZT': '',
        'p1$JiuYKN': '',
        'p1$JiuYSJ': '',
        'p1$GuoNei': '国内',
        'p1$ddlGuoJia$Value': '-1',
        'p1$ddlGuoJia': '选择国家',
        'p1$JinChuSQ': in_out,
        'p1$P_GuoNei$ShiFSH': in_shanghai,
        'p1$P_GuoNei$ShiFZX': in_school,
        'p1$P_GuoNei$XiaoQu': campus,
        'p1$P_GuoNei$JinXXQ': entry_campus,
        'p1$ddlSheng$Value': province,
        'p1$ddlSheng': province,
        'p1$ddlShi$Value': city,
        'p1$ddlShi': city,
        'p1$ddlXian$Value': county,
        'p1$ddlXian': county,
        'p1$ddlJieDao$Value': street,
        'p1$ddlJieDao': street,
        'p1$XiangXDZ': address,
        'p1$ShiFZJ': in_home,
        'p1$CengFWSS': out_province,
        'p1$DiHRQ': back_sh,
        'p1$GaoZDFXLJS': risk,
        'p1$FengXDQDL': '否',
        'p1$TongZWDLH': '否',
        'p1$CengFWH': '否',
        'p1$CengFWH_RiQi': '',
        'p1$CengFWH_BeiZhu': '',
        'p1$JieChu': '否',
        'p1$JieChu_RiQi': '',
        'p1$JieChu_BeiZhu': '',
        'p1$TuJWH': '否',
        'p1$TuJWH_RiQi': '',
        'p1$TuJWH_BeiZhu': '',
        'p1$QueZHZJC$Value': '否',
        'p1$QueZHZJC': '否',
        'p1$DangRGL': '否',
        'p1$GeLDZ': '',
        'p1$FanXRQ': '',
        'p1$WeiFHYY': '',
        'p1$ShangHJZD': '',
        'p1$DaoXQLYGJ': '无',
        'p1$DaoXQLYCS': '无',
        'p1$JiaRen_BeiZhu': '',
        'p1$SuiSM': '绿色',
        'p1$LvMa14Days': '是',
        'p1$Address2': '',
        'F_TARGET': f_target,
        'p1_pnlDangSZS_Collapsed': 'false',
        'p1_pImages_Collapsed': 'false',
        'p1_ContentPanel1_Collapsed': 'true',
        'p1_GeLSM_Collapsed': 'false',
        'p1_Collapsed': 'false',
        'F_STATE': f_state,
        'X-FineUI-Ajax': 'true',
    }
    return report_form


def getUnreadMsg(session):
    msg_url = 'https://selfreport.shu.edu.cn/MyMessages.aspx'
    msg_html = session.get(url=msg_url).text
    msg_raw = re.search(r'f2_state=(.*?);var', msg_html).group(1)
    msg = json.loads(msg_raw)['F_Items']
    blue_url = []
    red_url = []
    red_title = []
    for i in msg:
        if 'red' in i[1] or 'blue' in i[1]:
            url = 'https://selfreport.shu.edu.cn' + i[4]
            if 'blue' in i[1]:
                blue_url.append(url)
            elif 'red' in i[1]:
                title = re.search(r'标题：(.*?)</div>', i[1]).group(1)
                red_url.append(url)
                red_title.append(title)
    unread_msg = dict(blue_url=blue_url, red_url=red_url, red_title=red_title,
                      blue_count=len(blue_url), red_count=len(red_url))
    return unread_msg


def readUnreadMsg(session):
    unread_msg = getUnreadMsg(session)
    blue_count = unread_msg['blue_count']
    red_count = unread_msg['red_count']
    read_result = ''
    if blue_count + red_count > 0:
        print('检测到未读消息')
        for i, msg_url in enumerate(unread_msg['blue_url'] + unread_msg['red_url']):
            print('正在阅读第%s条消息' % (i + 1))
            try:
                session.get(url=msg_url, allow_redirects=False, timeout=10)
            except Exception as e:
                print(e)
                pass
            time.sleep(0.5)
        read_result = '阅读了'
        read_result += '%s条非必读消息' % blue_count if blue_count > 0 else ''
        read_result += '，%s条必读消息' % red_count if red_count > 0 else ''
        read_result += '：标题为《' + '》《'.join(unread_msg['red_title']) + '》' if red_count > 0 else ''
    return dict(red_count=red_count, result=read_result, username='')


def sendAllReadMsgResult(results: list, send_api, send_key):
    desp = ''
    for r in results:
        desp += r['username'] + ': ' + r['result'] + '\n\n' if r['red_count'] > 0 else ''
    if desp != '':
        title = '存在必读消息'
        return sendMsg(title, desp, send_api, send_key)
    return False


def getUnreportedDay(session, ignore_today=True):
    today = getTime().strftime("%Y-%m-%d")
    history_url = 'https://selfreport.shu.edu.cn/ReportHistory.aspx'
    index = session.get(url=history_url).text
    js_str = re.search('f2_state=(.*?);', index).group(1)
    items = json.loads(js_str)['F_Items']
    unreported_day = []
    if ignore_today and today in items[0][1]:
        items.pop(0)
    for i in items:
        if '未填报' in i[1]:
            date = re.search(r'\d{4}-\d{2}-\d{2}', i[1]).group(0)
            unreported_day.append(date)
    unreported_day.sort()
    return unreported_day


def reportUnreported(session, info, unreported_day):
    for post_day in unreported_day:
        _form = getReportForm(post_day, info)
        report_result = reportSingleUser(session, _form)
        if report_result == 1:
            print('补报%s成功' % post_day)
        else:
            print('补报%s失败' % post_day)
    print('补报结束')


def reportSingleUser(session, form, try_times=None, sleep_time=None, ignore_maintain=False):
    if not session:
        return -1
    if not form:
        return -2

    try_times = 5 if try_times is None else try_times
    sleep_time = 5 if sleep_time is None else sleep_time
    url = 'https://selfreport.shu.edu.cn/DayReport.aspx'
    report_times = 0
    while True:
        report_result = session.post(url=url, data=form)
        if '提交成功' in report_result.text:
            return 1
        elif '请上传' in report_result.text and '图片' in report_result.text:
            return -3
        elif 'p1_ctl01_btnReturn' in report_result.text and 'F.alert' not in report_result.text:
            # 表示当前IP被限制
            return -4
        elif '维护' in report_result.text and not ignore_maintain:
            return -5
        report_times += 1
        # print('填报失败，第%s次尝试' % report_times)
        if report_times > try_times:
            debug_key = [
                '__EVENTTARGET', 'p1$pnlDangSZS$DangSZS', 'p1$BaoSRQ', 'p1$P_GuoNei$ShiFSH', 'p1$P_GuoNei$ShiFZX',
                'p1$ShiFZJ', 'F_TARGET', 'p1$P_GuoNei$XiaoQu', 'p1$P_GuoNei$JinXXQ', 'p1$ddlJieDao', 'p1$JinChuSQ'
            ]
            debug_privacy_key = [
                'p1$ddlSheng$Value', 'p1$ddlSheng', 'p1$ddlShi$Value', 'p1$ddlShi', 'p1$ddlXian$Value', 'p1$ddlXian',
                'p1$XiangXDZ'
            ]
            debug_value = dict([(key, form.get(key, None)) for key in debug_key])
            debug_privacy_value = dict(
                [(key, f'***{str(form.get(key, None))[-1]}, length: {len(str(form.get(key, None)))}')
                 for key in debug_privacy_key]
            )
            debug_value.update(debug_privacy_value)
            print('调试信息：\n', json.dumps(debug_value, ensure_ascii=False, indent=4, sort_keys=True))
            print(report_result.text)
            return 0
        if sleep_time == 0:
            continue
        else:
            time.sleep(sleep_time)


def getUsers(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        users = yaml.load(f, Loader=yaml.FullLoader)['users']
    return users


def reportAllUsers(config_path, logs_path, post_day):
    users = getUsers(config_path)
    if not users:
        return False
    logs = getLogs(logs_path)
    if not logs:
        return False
    send_msg = getSendApi(config_path)
    if not send_msg:
        return False

    logs_time = getTime().strftime("%Y-%m-%d %H:%M:%S")
    read_msg_results = []
    logPrint('%s 开始填报所有用户' % logs_time)
    for i, username in enumerate(users):
        logPrint('开始填报 %s' % username)
        session = login(username, users[username][0])
        if session:
            read_msg_result = readUnreadMsg(session)
            read_msg_result['username'] = username
            read_msg_results.append(read_msg_result)

            _info = getLatestInfo(session)
            unreported_day = getUnreportedDay(session)
            if len(unreported_day) > 0:
                print('%s有%s天未填报，开始补报' % (username, len(unreported_day)))
                _info = getLatestInfo(session)
                reportUnreported(session, _info, unreported_day)
            _form = getReportForm(post_day, _info)
            report_result = reportSingleUser(session, _form)
        else:
            report_result = -1
        logs = updateLogs(logs, logs_time, username, report_result)
        if report_result == 1:
            print('填报成功')
        else:
            print('填报失败')
        if i < len(users) - 1:
            print("该用户填报结束，开始休眠60s......")
            time.sleep(60)
        else:
            logPrint("所有用户填报结束")
    saveLogs(logs_path, logs)
    sendAllReadMsgResult(read_msg_results, send_msg['api'], send_msg['key'])
    time.sleep(5)
    return True


def getSendApi(config_path):
    config = yaml.load(open(config_path, encoding='utf-8').read(), Loader=yaml.FullLoader)
    send_api = config.get('send_api', None)
    send_key = config.get('send_key', None)
    return {'api': send_api, 'key': send_key}


def sendMsg(title, desp, api, key):
    text = ''
    title += '，下次不要忘记填报哦~'
    try:
        if api == 1:
            url = "http://sctapi.ftqq.com/%s.send" % key
            data = {
                'text': title,
                'desp': desp,
            }
            text = requests.post(url, data=data).text
            result = json.loads(text)
            return result['code'] == 0
        elif api == 2:
            print('该消息推送接口已弃用，请更换其它接口')
            return False
        elif api == 3:
            tg_bot_key, tg_chat_id = key.split('@')
            url = 'https://api.telegram.org/bot%s/sendMessage' % tg_bot_key
            data = {
                'chat_id': tg_chat_id,
                'text': title + '\n' + desp,
            }
            text = requests.post(url, data=data).text
            result = json.loads(text)
            return result['ok']
        elif api == 4:
            url = 'https://api2.pushdeer.com/message/push'
            data = {
                "pushkey": key,
                "text": title,
                "desp": desp,
            }
            text = requests.post(url, data=data).text
            result = json.loads(text)
            return result['code'] == 0
        elif api == 5:
            url = "http://www.pushplus.plus/send"
            data = {
                'token': key,
                'title': title,
                'content': desp,
                'template': 'markdown'
            }
            headers = {'Content-Type': 'application/json'}
            body = json.dumps(data).encode(encoding='utf-8')
            text = requests.post(url, data=body, headers=headers).text
            result = json.loads(text)
            return result['code'] == 200
        else:
            return False

    except Exception as e:
        print(text)
        print(e)
        return False


def getLogs(logs_path, newest=False):
    try:
        with open(logs_path, 'r', encoding='utf-8') as f:
            logs = json.load(f)
    except Exception as e:
        print(e)
        return False
    if not newest:
        return logs
    else:
        try:
            report_time = max(logs.keys())
            return {report_time: logs[report_time]}
        except Exception as e:
            print(e)
            return False


def updateLogs(logs, logs_time, username, status):
    if logs_time not in logs:
        logs.update({logs_time: {}})
        if 'success' not in logs.get(logs_time, {}):
            logs[logs_time].update({'success': []})
        if 'fail' not in logs.get(logs_time, {}):
            logs[logs_time].update({'fail': []})

    success = logs[logs_time]['success']
    fail = logs[logs_time]['fail']

    if status == 1 and username not in success:
        success.append(username)
    elif username not in fail:
        fail.append(username)

    logs[logs_time]['success'] = success
    logs[logs_time]['fail'] = fail

    return logs


def saveLogs(logs_path, logs):
    with open(logs_path, 'w') as f:
        json.dump(logs, f)


def sendLogs(logs_path, config_path):
    send_msg = getSendApi(config_path)
    if send_msg['api'] == 0 or send_msg['key'] is None:
        print("未配置消息发送API")
        return False

    logs = getLogs(logs_path, newest=True)
    report_time = list(logs.keys())[0]

    title = ''
    desp = '时间：%s\n\n' % report_time
    success = logs[report_time].get('success')
    fail = logs[report_time].get('fail')

    if len(success):
        for username in success:
            title += username[4:] + '.'
            desp += '用户%s填报成功\n\n' % username
        title += '成功'

    if len(fail):
        for username in fail:
            title += username[4:] + '.'
            desp += '用户%s填报失败\n\n' % username
        title += '失败'
        desp += '请尽快查看控制台输出确定失败原因'

    send_times = 0
    while True:
        send_msg_result = sendMsg(title, desp, send_msg['api'], send_msg['key'])
        if send_msg_result != False and send_msg_result == True:
            return True
        send_times += 1
        if send_times > 10:
            return False


def checkEnv(config_path):
    try:
        users = getUsers(config_path)
        if len(users) == 0:
            print('未配置用户，请执行 python3 main.py add 添加用户')
            return False

        for username in users:
            if len(username) != 8:
                print(f'学号{username}有误')
                return False

    except Exception as e:
        print(e)
        return False
    return True


def initConfig(config_path):
    if not os.path.exists(config_path):
        try:
            with open(config_path, 'w') as f:
                config = {'send_api': 0, 'send_key': '', 'users': {}}
                yaml.dump(config, f)
        except Exception as e:
            print(e)
            return False
    return True


def setSendMsgApi(config_path):
    if not initConfig(config_path):
        return False
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    send_msg_api = [
        '未设置',
        '方糖气球 https://sct.ftqq.com/',
        '（该接口已弃用）推送加 https://pushplus.hxtrip.com/',
        'Telegram Bot (Key 的格式为 `BOT_TOKEN@CHAT_ID` )',
        'PushDeer https://github.com/easychen/pushdeer',
        '推送加PushPlus http://www.pushplus.plus/',
    ]
    send_api = config.get('send_api', 0)
    send_key = config.get('send_key', '')
    print('当前消息发送平台设置为：%s' % send_msg_api[send_api])
    print('支持的平台：')
    for i in range(1, len(send_msg_api)):
        print("%s. %s" % (i, send_msg_api[i]))
    while True:
        send_api = input("请选择：")
        try:
            send_api = int(send_api)
        except Exception as e:
            print(e)
            print('输入有误，重新输入')
            continue
        if send_api not in range(1, len(send_msg_api)):
            print('输入有误，重新输入')
        elif send_api == 2:
            print('该接口已弃用，请使用其它推送平台')
        else:
            break
    config['send_api'] = send_api

    print('当前Token为: %s' % send_key)
    send_key = input('设置Token：')
    config['send_key'] = send_key
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    return True


def addUser(config_path):
    while True:
        username = input('学号：')
        if len(username) == 8:
            break
        print('学号应为8位，请重新输入')

    password = input('密码：')
    if not login(username, password, try_once=True):
        print('学号或密码错误，请重新输入')
        return False

    new_user = {username: [password]}

    if not initConfig(config_path):
        return False

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    for username in list(config['users'].keys()):
        if len(username) != 8:
            config['users'].pop(username)

    config['users'].update(new_user)
    with open(config_path, 'w') as f:
        yaml.dump(config, f)

    return True


# 上报所有用户，用于测试
def test(config_path, logs_path):
    if not checkEnv(config_path):
        print("请检查是否已添加用户，确保config.yaml与logs.json可读写")
        print("运行 python3 main.py add 添加用户，运行 python3 main.py send 配置消息发送API")
        return False

    post_day = getTime().strftime("%Y-%m-%d")
    report_result = reportAllUsers(config_path, logs_path, post_day=post_day)
    if not report_result:
        print("填报失败，请检查错误信息")
    send_result = sendLogs(logs_path, config_path)
    if not send_result:
        print("Logs 发送失败，可能未配置消息发送API")
    # print("填报成功")
    return True


def logPrint(string=''):
    print()
    print("=" * 15)
    print(string) if string != '' else 0


def sleepCountdown(seconds):
    for i in range(seconds, 0, -10):
        print("休眠剩余%s秒" % i)
        time.sleep(10 if i > 10 else i)
    print("休眠结束")


def showIP():
    print("开始输出 IP 地址信息......")
    apis = {
        'Oversea': 'https://de5.backend.librespeed.org/getIP.php?isp=true',
        'SJTU': 'https://mirror.sjtu.edu.cn/speedtest/getIP?isp=true',
        'SHU': 'http://speedtest.shu.edu.cn/backend/getIP.php?isp=true',
    }

    ovpn_connected = False
    for api_name in apis:
        logPrint("%s IP Info: " % api_name)
        try:
            raw_ip = requests.get(apis[api_name], timeout=30).json()
            ip = raw_ip['rawIspInfo']
            if len(ip) == 0:
                ip = raw_ip
                if api_name == 'SHU':
                    ovpn_connected = True
            else:
                _ = ip['ip']
                ip.update({'ip': _[:int(len(_) / 2)] + '*' * int(len(_) / 2 + 1)})
            print(json.dumps(ip, ensure_ascii=False, indent=4, sort_keys=True))
        except Exception as e:
            print(e)
            print('Get %s IP Info Fail' % api_name)
    return ovpn_connected


def github():
    try:
        users = os.environ['users'].split(';')
        send = os.environ.get('send', '').split(',')
    except Exception as e:
        print(e)
        print('获取 GitHub Actions Secrets 变量出错，请尝试重新设置！')
        print('确保使用的是英文逗号和分号，且用户密码中也不包含英文逗号或分号')
        raise
    logPrint("GitHub Actions 填报开始\n若为第一次使用，耗时可能较长，请耐心等待......")
    ovpn_connected = showIP()
    logPrint('已接入校内VPN') if ovpn_connected else logPrint('未接入校内VPN')
    if not ovpn_connected:
        fake_ip = '59.79.' + '.'.join(str(random.randint(0, 255)) for _ in range(2))
        print('生成了随机IP: %s' % fake_ip)
    else:
        fake_ip = None
    post_day = getTime().strftime("%Y-%m-%d")
    suc_log = []
    xc_log = []
    err_log = []
    read_msg_results = []
    for i, user_info in enumerate(users):
        logPrint("正在为第%s位用户填报......" % (i + 1))
        try:
            username, password = user_info.split(',')
        except Exception as e:
            print(e)
            print('解析用户名和密码失败！')
            print('确保使用的是英文逗号和分号，且用户密码中也不包含英文逗号或分号')
            print('注意分号仅在间隔多个用户时才需要使用，USERS变量设置的内容末尾不需要带上分号')
            continue
        print('开始登录')
        session = login(username, password)
        if session:
            print('登录成功')
            if fake_ip is not None:
                headers = {
                    'X-Forwarded-For': fake_ip,
                }
                session.headers.update(headers)
            read_msg_result = readUnreadMsg(session)
            if read_msg_result['result'] != '':
                print(read_msg_result['result'])
            read_msg_result['username'] = username
            read_msg_results.append(read_msg_result)
            _info = getLatestInfo(session)
            unreported_day = getUnreportedDay(session)
            if len(unreported_day) > 0:
                print('该用户有%s天未填报，开始补报' % len(unreported_day))
                _info = getLatestInfo(session)
                reportUnreported(session, _info, unreported_day)
            _form = getReportForm(post_day, _info)
            report_result = reportSingleUser(session, _form)
        else:
            report_result = 0

        if report_result == 1:
            print('***填报成功')
            suc_log.append(username)
        elif report_result == -3:
            xc_log.append(username)
        elif report_result == -4:
            if not os.path.exists('use_ovpn'):
                logPrint('IP地址被限制，无法填报。将尝试连接校内VPN后再次填报......')
                with open('use_ovpn', 'w') as f:
                    f.write('1')
                print('休眠30s')
                sleepCountdown(30)
                exit(0)
            else:
                print('***连接校内VPN失败，填报失败') if not ovpn_connected else print('***填报失败，失败代码 -4')
                err_log.append(username)
        else:
            print('***填报失败')
            err_log.append(username)
        if i < len(users) - 1:
            print("该用户填报结束，开始休眠60s......")
            sleepCountdown(60)
        else:
            logPrint("所有用户填报结束")

    title = '每日一报'
    desp = ''
    if len(suc_log):
        for username in suc_log:
            desp += '用户%s填报成功\n\n' % username
        title += '%s位成功，' % len(suc_log)
    if len(err_log):
        for username in err_log:
            desp += '用户%s填报失败\n\n' % username
        title += '%s位失败，' % len(err_log)
        desp += '请尽快查看GitHub Actions日志输出确定失败原因\n\n如因学校网站改版导致的失败，可前往项目主页查看是否已适配更新'

    title += '共%s位' % len(users)

    logPrint()
    if len(send) == 2:
        send_api = int(send[0])
        send_key = send[1]
        send_result = sendMsg(title, desp, send_api, send_key)
        print('填报消息发送结果：%s' % send_result)
        time.sleep(5)
        send_read_result = sendAllReadMsgResult(read_msg_results, send_api, send_key)
        print('阅读消息发送结果：%s' % send_read_result)

    print(title)
    if err_log:
        print('填报失败用户：')
        for log in err_log:
            print('%s****%s' % (log[:2], log[-2:]))

    if xc_log:
        print('需要上传XC码用户：')
        for log in xc_log:
            print('%s****%s' % (log[:2], log[-2:]))

    if err_log or xc_log:
        exit(1)

    if len(suc_log + err_log + xc_log) < len(users):
        exit(1)


def isTimeToReport():
    now = getTime()
    if now.hour == 0 and now.minute >= 10:
        return 0
    elif now.hour == 1:
        return 3
    elif now.hour == 7:
        return 1
    # elif 20 <= now.hour <= 21:
    #     return 2
    return -1


def getGrabMode(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        grab_mode = yaml.load(f, Loader=yaml.FullLoader).get('grab_mode', True)
    return grab_mode


def grabRank(username, password, post_day):
    global GRAB_LOGS
    global READ_MSG_RESULTS

    try_times = 0
    while True:
        session = login(username, password)
        if session:
            break
        try_times += 1
        if try_times < 20:
            time.sleep(60)
            continue
        else:
            GRAB_LOGS['fail'].append(username)
            return False

    read_msg_result = readUnreadMsg(session)
    read_msg_result['username'] = username
    READ_MSG_RESULTS.append(read_msg_result)

    try_times = 0
    while True:
        _info = getLatestInfo(session)
        form = getReportForm(post_day, _info)
        if form:
            break
        try_times += 1
        if try_times < 10:
            time.sleep(10)
            continue
        else:
            GRAB_LOGS['fail'].append(username)
            return False

    now = getTime()
    sleep_time = 60 * (28 - now.minute)
    sleep_time = sleep_time if sleep_time > 0 and now.hour == 0 else 0
    time.sleep(sleep_time)

    while True:
        now = getTime()
        if (now.hour == 0 and now.minute == 29 and now.second >= 50) or now.hour != 0:
            report_result = reportSingleUser(session, form, try_times=900, sleep_time=0, ignore_maintain=True)
            if report_result == 1:
                GRAB_LOGS['success'].append(username)
                return True
            else:
                _info = getLatestInfo(session)
                form = getReportForm(post_day, _info)
                reportSingleUser(session, form)
                GRAB_LOGS['fail'].append(username)
                return False
        time.sleep(0.5)


def grabRankUsers(config_path, logs_path, post_day):
    users = getUsers(config_path)
    if not users:
        return False
    send_msg = getSendApi(config_path)
    if not send_msg:
        return False

    global GRAB_LOGS
    GRAB_LOGS = {'success': [], 'fail': []}
    global READ_MSG_RESULTS
    READ_MSG_RESULTS = []

    temp = {}

    logPrint('开始抢%s排名......' % post_day)
    for i, username in enumerate(users):
        temp[username] = threading.Thread(target=grabRank, args=(username, users[username][0], post_day))
        temp[username].start()
        if i < len(users) - 1:
            time.sleep(2 * 60)
    for username in users:
        temp[username].join()

    logs = getLogs(logs_path)
    logs_time = getTime().strftime("%Y-%m-%d %H:%M:%S")
    for username in GRAB_LOGS['success']:
        logs = updateLogs(logs, logs_time, username, True)
    for username in GRAB_LOGS['fail']:
        logs = updateLogs(logs, logs_time, username, False)
    saveLogs(logs_path, logs)
    sendAllReadMsgResult(READ_MSG_RESULTS, send_msg['api'], send_msg['key'])
    time.sleep(5)
    print('抢%s排名结束' % post_day)
    return True


def main(config_path, logs_path):
    if not checkEnv(config_path):
        print("请检查是否已添加用户，确保config.yaml与logs.json可读写")
        print("运行 python3 main.py add 添加用户，运行 python3 main.py send 配置消息发送API")
        return False

    grab_mode = getGrabMode(config_path)

    report_result = False
    while True:
        if not report_result:
            is_reported = False
            is_time = isTimeToReport()
            if (is_time == 0 or is_time == 3) and grab_mode and len(getUsers(config_path)) > 0:
                post_day = getTime().strftime("%Y-%m-%d")
                report_result = grabRankUsers(config_path, logs_path, post_day)
                is_reported = True
            elif is_time == 1 and len(getUsers(config_path)) > 0 and not grab_mode:
                post_day = getTime().strftime("%Y-%m-%d")
                report_result = reportAllUsers(config_path, logs_path, post_day=post_day)
                is_reported = True

            if is_reported:
                if not report_result:
                    print("填报失败，请检查错误信息")
                send_result = sendLogs(logs_path, config_path)
                if not send_result:
                    print("Logs 发送失败，可能未配置消息发送API")

        if isTimeToReport() == -1:
            report_result = False
        time.sleep(5 * 60)
