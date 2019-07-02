import logging
import pickle
import hashlib
import os

import tqdm
import pytesseract
import cv2
import numpy as np
import pdf2image
from sklearn.cluster import KMeans

import 表格识别
import 输出doc
import 旋转矫正
import 目录识别

from 缓存 import 缓存


pytesseract.pytesseract.tesseract_cmd = r"D:\Program Files\Tesseract-OCR-5.0-Alpha\tesseract.exe"
logging.basicConfig(level=logging.DEBUG)


def draw_box(img, left, top, width, height, level):
    cv2.rectangle(img, (left, top), (left + width, top + height), (0, 211, 211), 5)


class 星:
    def __init__(self, pdf_path=None, 黑度阈值=166):
        self.pdf文件名 = pdf_path
        self.黑度阈值 = 黑度阈值

    def 龙(self, dpi=600):
        logging.debug('将pdf转为图片……')
        图片组 = pdf2image.convert_from_path(self.pdf文件名, dpi=dpi, thread_count=4)
        图片组 = [np.array(图) for 图 in 图片组]
        logging.debug('转word……')
        页组 = [self.单图片提取(图) for 图 in tqdm.tqdm(图片组, ncols=60)]
        return 页组

    @缓存
    def ocr(self, img):
        ocr信息 = pytesseract.image_to_data(img, lang='chi_sim', output_type='dict')
        return ocr信息

    def 行切(self, ocr信息, img=None):
        a = []
        for n in range(len(ocr信息['level'])):
            a.append({})
            now = a[-1]
            for i, x in ocr信息.items():
                now[i] = x[n]
            now['h'] = (now['block_num'], now['par_num'], now['line_num'])

        dv = {}
        for i in a:
            if i['level'] <= 3:
                None
            if i['level'] == 4:
                dv[i['h']] = {
                    'left': i['left'],
                    'top': i['top'],
                    'right': i['left'] + i['width'],
                    'bottom': i['top'] + i['height'],
                    'width': i['width'],
                    'height': i['height'],
                    '内容': [],
                }
            if i['level'] == 5:
                dv[i['h']]['内容'].append((i['text'], str(i['conf'])))

        dv = [x for i, x in dv.items() if any([j != ' ' for j, _ in x['内容']])]

        return dv

    def 行距提取(self, 行信息):
        行距组 = [后['top'] - 前['top'] for 前, 后 in zip(行信息[:-1], 行信息[1:])]
        行高组 = [行['height'] for 行 in 行信息]
        中位行高 = sorted(行高组)[len(行高组) // 2]
        有效行距组 = [i for i in 行距组 if i < 3 * 中位行高]
        return 有效行距组

    def 连接行距分析(self, 行距):
        estimator = KMeans(n_clusters=2)
        estimator.fit(np.array(行距).reshape(-1, 1))

        center = estimator.cluster_centers_
        小标签 = np.where(center == np.min(center))[0][0]

        label_pred = estimator.labels_

        小标签组 = [x for label, x in zip(label_pred, 行距) if label == 小标签]

        return max(小标签组)

    def 行连接(self, 行信息, 连接行距, c, 左右阈值=0.01):
        极左 = min([i['left'] for i in 行信息])
        极右 = max([i['right'] for i in 行信息])
        d = c * 左右阈值
        logging.debug({'连接行距': 连接行距, '极左': 极左, '极右': 极右})
        段落信息 = []
        for 当前行 in 行信息:
            if 当前行['left'] > 极左 + 5 * d and 当前行['right'] < 极右 - 5 * d \
                    and -5 * d < (当前行['right'] + 当前行['left']) - c < 5 * d:
                段落信息.append({
                    'top': 当前行['top'],
                    'right': 当前行['right'],
                    '行组': [当前行],
                    '样式': '居中',
                })
            else:
                当前行['缩进'] = 当前行['left'] - 极左
                if not 段落信息 \
                        or 当前行['top'] - 段落信息[-1]['行组'][-1]['top'] > 连接行距:
                    段落信息.append({
                        'top': 当前行['top'],
                        'right': 当前行['right'],
                        '行组': [当前行],
                        '样式': None,
                    })
                else:
                    最后一段 = 段落信息[-1]
                    if 当前行['left'] < 极左 + d and 最后一段['right'] > 极右 - d:
                        最后一段['行组'][-1]['内容'] += 当前行['内容']
                    else:
                        段落信息[-1]['行组'].append(当前行)
                    最后一段['right'] = 当前行['right']

        return 段落信息

    def 去除文字(self, 图, 行信息):
        alice = 图.copy()
        for d in 行信息:
            alice[d['top']:d['top'] + d['height'], d['left']:d['left'] + d['width']] = 255
        return alice

    def 取残(self, alice):
        imgray = cv2.cvtColor(alice, cv2.COLOR_BGR2GRAY)
        ret, imgray = cv2.threshold(imgray, 127, 255, 0)

        r, c = imgray.shape
        d = r // 64 * 2 + 1

        imgray = cv2.blur(imgray, (d, d), 0)
        ret, thresh = cv2.threshold(imgray, 252, 255, 1)
        cv2.imwrite('./alice0.png', thresh)

        contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        座标 = []
        for contour in contours:
            left, top = np.min(contour, axis=0).flatten()
            right, bottom = np.max(contour, axis=0).flatten()
            座标.append({
                'top': top,
                'bottom': bottom,
                'left': left,
                'right': right,
            })
        座标 = sorted(座标, key=lambda x: x['top'])
        去重座标 = []
        for i, d in enumerate(座标):
            for d2 in 座标[:i]:
                if d['bottom'] < d2['bottom'] and d['left'] > d2['left'] and d['right'] < d2['right']:
                    break
            else:
                去重座标.append(d)
        return 去重座标

    def 单图片提取(self, img):
        img[np.where(img > self.黑度阈值)] = 255
        r, c, _ = img.shape

        img = 旋转矫正.自动旋转矫正(img)

        净图, 表格组 = 表格识别.分割表格(img)
        print(表格组)

        净图, 省略号组 = 目录识别.目录识别(净图)

        ocr信息 = self.ocr(净图)

        行信息 = self.行切(ocr信息, 净图)

        有效行距组 = self.行距提取(行信息)
        if len(有效行距组) >= 2:
            连接行距 = self.连接行距分析(有效行距组)
        else:
            连接行距 = 0

        段落信息 = self.行连接(行信息, 连接行距, c)

        alice = self.去除文字(净图, 行信息)

        图块组 = self.取残(alice)

        for 块 in 图块组:
            块['内容'] = img[块['top']:块['bottom'], 块['left']:块['right']]
            净图[块['top']:块['bottom'], 块['left']:块['right']] //= 2

        for d in 行信息:
            draw_box(净图, d['left'], d['top'], d['width'], d['height'], 4)
        cv2.imwrite('./ans.png', 净图)

        return {
            '段落信息': 段落信息,
            '表格组': 表格组,
            '图块组': 图块组
        }


# 页组 = 星('./data/SYT 6662.5-2014.pdf').龙(dpi=600)
# 输出doc.输出('mae.docx', 页组)


img = cv2.imread('./data/t5.png')
页 = 星().单图片提取(img)

输出doc.输出('mae.docx', [页])
