# -*- coding:utf-8 -*-
"""电子科大抢课模块"""
import threading
import time
import signal
import requests


__all__ = ["get_open_entrance", "choose_course",
           "catch_course", "display_catch_course_result"]
__CATCH_COURSE_POST_URL = "http://eams.uestc.edu.cn/eams/stdElectCourse!batchOperator.action?profileId="
__CATCH_COURSE_URL = "http://eams.uestc.edu.cn/eams/stdElectCourse!defaultPage.action?electionProfile.id="
__EXIT_THREAD = False
__CATCH_COURSE_RESULT = []
__EXIT_TEXT_LIST = ['本批次', '只开放给', '学分已达上限', '现在未到选课时间', '超过限选门数', '冲突']
#__EXIT_TEXT_LIST = ['本批次', '只开放给', '学分已达上限']


def __get_mid_text(text, left_text, right_text, start=0):
    """获取中间文本"""
    left = text.find(left_text, start)
    if left == -1:
        return ('', -1)
    left += len(left_text)
    right = text.find(right_text, left)
    if right == -1:
        return ('', -1)
    return (text[left:right], right)


def __get_open_url_data(login_session, todo_list, ret_list, thread_lock, display_result):
    """读取选课网页"""
    while True:
        thread_lock.acquire()
        if todo_list:
            now_get = todo_list.pop()
            if display_result and now_get % 100 == 0:
                print(now_get)

        else:
            thread_lock.release()
            break

        thread_lock.release()
        while True:

            response = login_session.get(__CATCH_COURSE_URL + str(now_get))
            if '学号' in response.text:
                thread_lock.acquire()
                ret_list.append(now_get)
                thread_lock.release()

            # 我也忘了下面这句干嘛的了
            if '(possibly due to' not in response.text:
                break


def get_open_entrance(login_session, start_entrance=0, end_entrance=2000, max_thread=100,
                      display_result=False):
    """获取选课通道 返回开放通道的list"""
    ret_list = []
    todo_list = []
    threads = []
    thread_lock = threading.Lock()
    for i in range(end_entrance, start_entrance - 1, -1):
        todo_list.append(i)
    for i in range(0, max_thread):
        threads.append(threading.Thread(target=__get_open_url_data,
                                        args=(login_session, todo_list,
                                              ret_list, thread_lock, display_result)))
        threads[-1].start()

    # 阻塞
    for thread in threads:
        thread.join()

    ret_list.sort()
    return ret_list


def choose_course(login_session, entrance, class_id, choose):
    """选课 class_id为int"""
    postdata = {'operator0': '%s:%s:0' % (str(class_id), str(choose).lower())}
    # 不写会报未到选课时间
    login_session.get(__CATCH_COURSE_URL + str(entrance))
    response = login_session.post(
        __CATCH_COURSE_POST_URL + str(entrance), data=postdata)
    info, end = __get_mid_text(
        response.text, 'text-align:left;margin:auto;">', '</br>')
    
    #现在未到选课时间格式不同 单独处理
    if '现在未到选课时间' in response.text:
        info = '现在未到选课时间，无法选课！'
    elif end == -1:
        info = '网络错误！'
    info = info.replace(' ', '').replace('\n', '').replace('\t', '')
    info += '  id:%s  entrance:%s' % (class_id, entrance)
    return info


def __catch_course(login_session, entrance, class_id, thread_name,
                   thread_lock, ret_dict, choose, sleep, display_text, force):
    count = 0
    exit_thread = False
    while True:
        exit_thread = __EXIT_THREAD
        info = choose_course(login_session, entrance, class_id, choose)
        count += 1
        if display_text:
            thread_lock.acquire()
            print('%s正在进行第%d次尝试\n%s' % (thread_name, count, info))
            thread_lock.release()

        for exit_text in __EXIT_TEXT_LIST:
            if exit_text in info:
                if force == True and exit_text == '现在未到选课时间':
                    continue
                else:
                    ret_dict[class_id][entrance] = 1
                break
        if '成功' in info:
            ret_dict[class_id][entrance] = 0
        if ret_dict[class_id][entrance] != None:
            exit_thread = True

        thread_lock.acquire()
        if exit_thread:
            __CATCH_COURSE_RESULT.append(info)
            thread_lock.release()
            break

        thread_lock.release()
        time.sleep(sleep)

def catch_course(login_session, entrance_list, class_id_list, choose=True, sleep=0, max_thread=5,
                 display_text=False, force=False):
    """抢课
    该函数执行后除非所有课程抢到，否则不会结束
    以及该函数会捕获中断信号
    中断后会输出选课结果
    将会返回一个dict 表示选课结果
    entrance与class_id均为int
    若dict为0表示选课成功，为其他值则为失败"""
    global __EXIT_THREAD
    __EXIT_THREAD = False
    __CATCH_COURSE_RESULT.clear()
    signal.signal(signal.SIGINT, catch_course_quit)
    signal.signal(signal.SIGTERM, catch_course_quit)
    threads = []
    ret_dict = {}
    thread_lock = threading.Lock()

    for class_id in class_id_list:
        ret_dict[class_id] = {}
        for entrance in entrance_list:
            ret_dict[class_id][entrance] = None
            for i in range(max_thread):
                threads.append(
                    threading.Thread(
                        target=__catch_course, args=(
                            login_session, entrance,
                            class_id, '[%d-%d-Thread-%d]' % (
                                class_id, entrance, (i + 1)),
                            thread_lock, ret_dict, choose, sleep, display_text, force)))
                threads[-1].start()

    for thread in threads:
        thread.join()

    # 输出抢课结果
    if display_text:
        display_catch_course_result()

    for class_id in ret_dict:
        for entrance in ret_dict[class_id]:
            if ret_dict[class_id][entrance] is None:
                ret_dict[class_id][entrance] = 1

    return ret_dict


def catch_course_quit(signum, frame):
    """键盘中断时调用"""
    global __EXIT_THREAD
    __EXIT_THREAD = True
    while threading.activeCount() > 1:
        pass


def display_catch_course_result():
    """输出抢课结果"""
    print('正在停止抢课')
    print('\n\n\n')
    print('抢课结果如下:')
    for i in range(len(__CATCH_COURSE_RESULT)):
        print(str(i + 1) + '.' + __CATCH_COURSE_RESULT[i])
