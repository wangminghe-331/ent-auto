#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
娱乐自动监控台 - 云端刷新脚本
由 GitHub Actions 每日三班触发：抓四平台热点 -> 选热点出配文 -> 写 data.json -> commit。
完全不依赖本地电脑。出文用 LLM API（key 走 Secret，无 key 走模板），不再配图。
"""
import os
import re
import json
import time
import datetime

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}


# ---------------- 基础工具 ----------------
def fetch(url, timeout=15, extra=None):
    h = dict(HEADERS)
    if extra:
        h.update(extra)
    try:
        r = requests.get(url, headers=h, timeout=timeout)
        r.encoding = r.apparent_encoding or "utf-8"
        if r.status_code == 200:
            return r.text
    except Exception as e:
        print(f"[fetch fail] {url}: {e}")
    return ""


def to_int(n):
    try:
        return int(n)
    except Exception:
        return 0


# ---------------- 各平台抓取 ----------------
def weibo_hot():
    out = []
    # 优先微博 ajax 热搜接口
    txt = fetch("https://weibo.com/ajax/side/hotSearch")
    if txt:
        try:
            j = json.loads(txt)
            for it in j.get("data", {}).get("realtime", [])[:8]:
                w = it.get("word") or it.get("topic")
                if w:
                    out.append((w.strip(), to_int(it.get("num"))))
        except Exception as e:
            print("[weibo parse]", e)
    if not out:
        # 回退 tophub 微博榜
        html = fetch("https://tophub.today/n/KqndgxeLl9")
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for tr in soup.select("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    out.append((tds[1].get_text(strip=True), 0))
    return out[:6]


def douyin_hot():
    out = []
    html = fetch("https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/")
    if html:
        try:
            j = json.loads(html)
            for it in j.get("word_list", [])[:8]:
                out.append((it.get("word", ""), to_int(it.get("hot_score") or it.get("score"))))
        except Exception as e:
            print("[douyin parse]", e)
    if not out:
        html = fetch("https://tophub.today/n/DpQvNABoNE")
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for tr in soup.select("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    out.append((tds[1].get_text(strip=True), 0))
    return out[:6]


def xiaohongshu_hot():
    out = []
    html = fetch("https://www.46.la/tool/xiaohongshu-hot")
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a")[:12]:
            t = a.get_text(strip=True)
            if t and len(t) > 1:
                out.append((t, 0))
    return out[:6]


def bilibili_hot():
    out = []
    url = "https://api.bilibili.com/x/web-interface/ranking/v2?rid=0"
    txt = fetch(url, extra={"User-Agent": UA, "Referer": "https://www.bilibili.com"})
    if txt:
        try:
            j = json.loads(txt)
            for it in j.get("data", {}).get("list", [])[:8]:
                out.append((it.get("title", ""), to_int(it.get("stat", {}).get("view"))))
        except Exception as e:
            print("[bili parse]", e)
    return out[:6]


PLATFORMS = {
    "微博": weibo_hot,
    "抖音": douyin_hot,
    "小红书": xiaohongshu_hot,
    "B站": bilibili_hot,
}


# ---------------- 出文（LLM 或模板） ----------------
def template_text(topic, platform):
    tail = {
        "微博": "你们刷到这条热搜了吗？评论区聊聊～",
        "抖音": "这条是不是也被你刷到过？说说你的看法～",
        "小红书": "有没有也在看这个的？一起来聊聊～",
        "B站": "这东西你们看了吗？弹幕见～",
    }.get(platform, "你们刷到了吗？评论区聊聊～")
    return (f"【{topic}】\n\n"
            f"「{topic}」这两天真的到处都在刷，一打开手机全是它。\n"
            f"看了一圈，就一个感觉：它确实把人戳到了，不是那种硬炒出来的热度。\n"
            f"{tail}")


def llm_text(topic, platform):
    key = os.environ.get("LLM_API_KEY")
    if not key:
        return template_text(topic, platform)
    url = os.environ.get("LLM_API_URL") or "https://api.deepseek.com/chat/completions"
    model = os.environ.get("LLM_MODEL") or "deepseek-chat"
    prompt = (f"你是一个社交媒体内容创作者。请基于热点「{topic}」，直接写一篇适合{platform}平台发布的图文笔记正文。"
              f"要求：像真人随手写的分享，口语、有温度、不要列要点、不要分点分析、不要解释写作思路，控制在200字以内。"
              f"只输出正文文案本身。")
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8, "max_tokens": 400}
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {key}",
                                         "Content-Type": "application/json"},
                          json=body, timeout=45)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("[llm fail]", e)
    return template_text(topic, platform)


# ---------------- 主流程 ----------------
def load_old():
    try:
        with open("data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    old = load_old()
    today = datetime.date.today().isoformat()
    hotspots = []
    hid = 0
    for plat, fn in PLATFORMS.items():
        try:
            items = fn()
        except Exception as e:
            print(f"[{plat} error]", e)
            items = []
        for rank, (topic, heat) in enumerate(items, 1):
            if not topic:
                continue
            hid += 1
            hotspots.append({
                "id": f"{plat[0]}{today}-{hid:02d}",
                "platform": plat,
                "topic": topic,
                "heat": heat,
                "source": "",
                "note": (f"#{plat} 实时热榜第{rank}位" if heat else f"#{plat} 热点"),
                "capturedAt": today,
            })

    old_posts = [p for p in (old or {}).get("posts", [])
                 if "占位" not in (p.get("text") or "")]
    # 只保留文案，不再配图：清掉历史图文里的图片字段
    for p in old_posts:
        p["image"] = ""
    # 选 1-2 条高热度（或前两条）做配文
    candidates = sorted([h for h in hotspots if h["heat"] > 0], key=lambda x: -x["heat"])
    if not candidates:
        candidates = hotspots[:2]
    new_posts = []
    for h in candidates[:2]:
        text = llm_text(h["topic"], h["platform"])
        new_posts.append({
            "id": f"p-{int(time.time())}-{h['platform']}",
            "platform": h["platform"],
            "topic": h["topic"],
            "text": text,
            "image": "",
            "at": today,
        })
    final_posts = (old_posts + new_posts)[-8:]

    data = {
        "updatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "build": datetime.datetime.now().strftime("%Y%m%d-%H%M"),
        "cycle": (old or {}).get("cycle", 0) + 1,
        "driver": "GitHub Actions 云端定时",
        "hotspots": hotspots,
        "posts": final_posts,
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"written data.json: {len(hotspots)} hotspots, {len(final_posts)} posts, cycle {data['cycle']}")


if __name__ == "__main__":
    main()
