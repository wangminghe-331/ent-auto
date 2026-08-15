#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
娱乐自动监控台 - 云端刷新脚本
由 GitHub Actions 每小时触发：抓四平台热点 -> 选热点出图文 -> 写 data.json -> commit。
完全不依赖本地电脑。出图用 Pollinations.ai（免费、无需 key，仅嵌 URL）；出文用 LLM API（key 走 Secret）。
"""
import os
import re
import json
import time
import datetime
import urllib.parse

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
    return (f"【{topic}】\n\n"
            f"最近「{topic}」热度很高，不少人都在聊。\n"
            f"三个角度：① 它为什么突然火；② 背后值得关注的点；③ 你自己的看法。\n"
            f"一句话文案：『{topic}，你怎么看？』评论区聊聊～")


def llm_text(topic, platform):
    key = os.environ.get("LLM_API_KEY")
    if not key:
        return template_text(topic, platform)
    url = os.environ.get("LLM_API_URL") or "https://api.deepseek.com/chat/completions"
    model = os.environ.get("LLM_MODEL") or "deepseek-chat"
    prompt = (f"你是一个社交媒体内容创作者。请基于以下热点话题，写一篇适合{platform}平台发布的图文笔记。"
              f"要求：像真人笔记/短文，含吸引人的标题、切入角度、2-3个要点、一句可复用的文案。"
              f"话题：{topic}。只输出正文，不要解释，控制在200字以内。")
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


# ---------------- 出图（Pollinations，免费，仅嵌 URL） ----------------
def pollinations_image_url(prompt, seed=None):
    p = urllib.parse.quote(prompt[:200])
    params = {"width": 1024, "height": 768, "nologo": 1,
              "model": "flux", "seed": seed if seed is not None else int(time.time()) % 100000}
    q = urllib.parse.urlencode(params)
    return f"https://image.pollinations.ai/prompt/{p}?{q}"


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
    # 选 1-2 条高热度（或前两条）做图文
    candidates = sorted([h for h in hotspots if h["heat"] > 0], key=lambda x: -x["heat"])
    if not candidates:
        candidates = hotspots[:2]
    new_posts = []
    for h in candidates[:2]:
        text = llm_text(h["topic"], h["platform"])
        img = pollinations_image_url(h["topic"] + " 旅行 生活 氛围感 摄影 质感")
        new_posts.append({
            "id": f"p-{int(time.time())}-{h['platform']}",
            "platform": h["platform"],
            "topic": h["topic"],
            "text": text,
            "image": img,
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
