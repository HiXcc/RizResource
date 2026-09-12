import base64
import UnityPy
import os
import json
from acbtowav import convert_acb_to_wav,get_duration_vgmstream
import asyncio
from curl_cffi import requests
import time
import aiofiles
from zipfile import ZipFile

# 全局并发信号量，限制同时进行的请求/处理数量
SEM = asyncio.Semaphore(30)

header = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0"
}

class ByteReader:
    def __init__(self, data):
        self.data = data
        self.position = 0

    def readInt(self):
        self.position += 4
        return self.data[self.position - 4] ^ self.data[self.position - 3] << 8 ^ self.data[self.position - 2] << 16

def safe_string(string):
    """保留原检测逻辑，但若频繁调用可考虑缓存或简化"""
    try:
        string.encode("gbk")
        return True
    except UnicodeEncodeError:
        return False

def color_convert(color):
    return (round(color["r"]*255), round(color["g"]*255), round(color["b"]*255), round(color["a"]*255))

async def getver_async(session):
    """异步获取最新版本信息"""
    headers = {"game_id": "pigeongames.rizline"}
    resp = await session.get("https://rizserver.pigeongames.net/game/server_api/v1/dis", headers=headers, verify=False)
    return resp.json()["configs"][0]["resourceUrl"]

async def fetch(session, bundle_name, ver):
    """获取默认配置、生物、成就、周任务等文本资源（仅示例，原逻辑保留）"""
    verlist = ver["verlist"]
    if bundle_name in verlist:
        verlist.insert(0, ver[bundle_name])
    resp = None
    for v in verlist:
        url = f"https://rizlineasset.pigeongames.net/versions/{v}/Android/{bundle_name}"
        resp = await session.get(url, headers=header, impersonate="chrome120", timeout=600)
        if resp.status_code != 404:
            break
    if resp and resp.status_code < 300:
        bundle = resp.content
        env = await asyncio.to_thread(UnityPy.load, bundle)
        for obj in env.objects:
            data = await asyncio.to_thread(obj.read)
            if hasattr(data, "m_Name"):
                if data.m_Name == "Default":
                    d = await asyncio.to_thread(obj.read_typetree)
                    if "m_GameObject" in d:
                        return d
                if data.m_Name in ("zh-Hans.bio", "zh-Hans.achievement", "zh-Hans.weeklyTask"):
                    with open(f"{data.m_Name}.txt", "wb") as tf:
                        tf.write(data.m_Script.encode())
    return False

async def fetch_resource(session, bundle_name, ver, key):
    """下载单个资源，处理谱面/曲绘/音频"""
    async with SEM:
        verlist = ver["verlist"]
        if bundle_name in verlist:
            verlist.insert(0, ver[bundle_name])
        resp = None
        for v in verlist:
            url = f"https://rizlineasset.pigeongames.net/versions/{v}/Android/{bundle_name}"
            resp = await session.get(url, headers=header, impersonate="chrome120", timeout=600)
            if resp.status_code != 404:
                break
        if resp is None or resp.status_code >= 300:
            print(f"下载失败: {bundle_name}, url:{url}, 状态码: {resp.status_code if resp else '无响应'}")
            return False

        bundle = resp.content
        if bundle_name.startswith("cridata_assets_criaddressables/"):
            # 音频资源：提取文件名并转换
            path = key.removeprefix("CriAddressables/")
            if ".acb" in path:
                file_name = path[:path.index(".acb") + 4]
            else:
                file_name = path
            if not safe_string(file_name):
                file_name = file_name.encode("gbk", errors="ignore").decode("utf-8")
            acb_path = f"music-acb/{file_name}"
            with open(acb_path, "wb") as m:
                m.write(bundle)
            # 转换音频，放入线程池避免阻塞
            success = await asyncio.to_thread(convert_acb_to_wav, acb_path, "music-wav")
            if not success:
                print(f"转换失败: {file_name}")
        else:
            # 谱面或曲绘（Unity 资源）
            env = await asyncio.to_thread(UnityPy.load, bundle)
            for obj in env.objects:
                data = await asyncio.to_thread(obj.read)
                if obj.type.name == "TextAsset":  # 谱面 JSON
                    content = data.m_Script.encode()
                    out_path = f"chart/{key}.json"
                    with open(out_path, "wb") as f:
                        f.write(content)
                elif obj.type.name == "Texture2D":  # 曲绘
                    if key.endswith("HiRes"):
                        save_name = key.removesuffix(".HiRes")
                        save_path = f"illustration-HiRes/{save_name}.png"
                    else:
                        save_path = f"illustration/{key}.png"
                    await asyncio.to_thread(data.image.save, save_path)
        return True

async def info_get(bundle_list, ver):
    """解析资源索引，生成歌曲信息 JSON"""
    # 寻找特定 bundle 的 hash
    for bundle in bundle_list:
        if bundle["m_BundleName"] == "bc06b7df85213f57979af8925a2d787a":
            info_bundle = f"{bundle['m_Hash']}.bundle"
        elif bundle["m_BundleName"] == "082fc974cd54ee688f9245a33ac24459":
            bio_bundle = f"{bundle['m_Hash']}.bundle"
        elif bundle["m_BundleName"] == "27f38416a97358ea81fae5408729ff53":
            weekly_bundle = f"{bundle['m_Hash']}.bundle"
        elif bundle["m_BundleName"] == "913a07462eb62aace70586d300a841eb":
            achievement_bundle = f"{bundle['m_Hash']}.bundle"

    urls = [info_bundle, bio_bundle, weekly_bundle, achievement_bundle]
    async with requests.AsyncSession() as session:
        tasks = [fetch(session, url, ver) for url in urls]
        results = await asyncio.gather(*tasks)
    # 过滤出非空结果（第一个有效）
    d = next((x for x in results if x), None)
    if not d:
        raise ValueError("无法获取Default资源")

    # 构建快速查找字典
    musics_map = {m["id"]: m for m in d["musics"]}
    illustrations_map = {ill["id"]: ill for ill in d["illustrations"]}
    charts_map = {ch["id"]: ch for ch in d["charts"]}

    infos = []
    for song in d["levels"] + d["discOLevels"]:
        song_id = song["id"]
        music_id = song["musicId"]
        ill_id = song["illustrationId"]
        chart_ids = song["chartIds"]

        music_dict = musics_map.get(music_id)
        ill_dict = illustrations_map.get(ill_id)
        if not music_dict or not ill_dict:
            continue

        info = {
            "id": song_id,
            "chart_id": chart_ids,
            "music_id": music_id,
            "illustration_id": ill_id,
            "chap": song["discName"],
            "name": music_dict["musicName"],
            "composer": music_dict["artist"],
            "themeUiColor": color_convert(music_dict["themeUiColor"]),
            "pst": music_dict["previewStartTime"],
            "pet": music_dict["previewOverTime"],
            "illustrator": ill_dict["artist"],
        }
        if os.path.exists(f"music-acb/{music_id.lower()}.acb"):
            info["length"] = get_duration_vgmstream(f"music-acb/{music_id.lower()}.acb")
        else:
            info["length"] = 0
        diff_list = []
        for ch_id in chart_ids:
            chart_dict = charts_map.get(ch_id)
            if chart_dict:
                level = chart_dict["level"]
                info[level] = {
                    "diff": round(chart_dict["difficulty"], 1),
                    "charter": chart_dict["designer"],
                }
                diff_list.append(level)
        info["diffs"] = diff_list
        infos.append(info)

    async with aiofiles.open("info.json", "w", encoding="utf-8") as f:
        await f.write(json.dumps(infos, ensure_ascii=False))
    async with aiofiles.open("layout.json", "w", encoding="utf-8") as f:
        await f.write(json.dumps(d["layoutColors"], ensure_ascii=False))
    async with aiofiles.open("diffcolors.json", "w", encoding="utf-8") as f:
        await f.write(json.dumps(d["difficultyColors"], ensure_ascii=False))
    async with aiofiles.open("default_raw.json", "w", encoding="utf-8") as f:
        await f.write(json.dumps(d, ensure_ascii=False))

    print("info done.")
    return infos

async def resource_get(data, verlist):
    """解析 catalog，构建资源列表并下载"""
    key = base64.b64decode(data["m_KeyDataString"])
    bucket = base64.b64decode(data["m_BucketDataString"])
    entry = base64.b64decode(data["m_EntryDataString"])

    table = []
    reader = ByteReader(bucket)
    for _ in range(reader.readInt()):
        key_position = reader.readInt()
        key_type = key[key_position]
        key_position += 1
        if key_type == 0:
            length = key[key_position]
            key_position += 4
            key_value = key[key_position:key_position + length].decode()
        elif key_type == 1:
            length = key[key_position]
            key_position += 4
            key_value = key[key_position:key_position + length].decode("utf16")
        elif key_type == 4:
            key_value = key[key_position]
        else:
            raise BaseException(key_position, key_type)
        for i in range(reader.readInt()):
            entry_position = reader.readInt()
            entry_value = entry[4 + 28 * entry_position:4 + 28 * entry_position + 28]
            entry_value = entry_value[8] ^ entry_value[9] << 8
        table.append([key_value, entry_value])

    # 解析引用
    for i in range(len(table)):
        if table[i][1] != 65535:
            table[i][1] = table[table[i][1]][0]

    Resource = []
    extra = []
    for i in range(len(table) - 1, -1, -1):
        if not isinstance(table[i][0], str) or not isinstance(table[i][1], str):
            del table[i]
            continue
        if table[i][0].startswith("chart"):
            Resource.append(table[i])
        elif table[i][0].startswith(("illustration", "altIllustration")):
            Resource.append(table[i])
        elif table[i][0].startswith("CriAddressables/"):
            Resource.append(table[i])
        else:
            extra.append(table[i])

    os.makedirs("Unpack_log", exist_ok=True)
    with open("Unpack_log/all_resource", "w", encoding="utf-8") as f:
        for item in Resource + extra:
            f.write(str(item) + "\n")
    for name, condition in [("chart_log", lambda x: x[0].startswith("chart")),
                            ("illustration_log", lambda x: x[0].startswith(("illustration", "altIllustration"))),
                            ("music_log", lambda x: x[0].startswith("CriAddressables/"))]:
        with open(f"Unpack_log/{name}", "w", encoding="utf-8") as f:
            for item in Resource:
                if condition(item):
                    f.write(str(item) + "\n")

    # 构建下载任务列表
    urls = []
    for key_val, entry_val in Resource:
        if key_val.startswith(("chart", "illustration", "altIllustration")):
            # 检查是否已存在
            if key_val.startswith("chart") and os.path.exists(f"chart/{key_val}.json"):
                continue
            if key_val.startswith("illustration") and key_val.endswith("HiRes"):
                base = key_val.removesuffix(".HiRes")
                if os.path.exists(f"illustration-HiRes/{base}.png"):
                    continue
            elif key_val.startswith("illustration") and not key_val.endswith("HiRes"):
                if os.path.exists(f"illustration/{key_val}.png"):
                    continue
            url = entry_val
        elif key_val.startswith("CriAddressables/") and not entry_val.startswith("crilocaldata_assets_all"):
            path = key_val.removeprefix("CriAddressables/")
            file_name = path[:path.index(".acb") + 4] if ".acb" in path else path
            if not safe_string(file_name):
                file_name = file_name.encode("gbk", errors="ignore").decode("utf-8")
            if os.path.exists(f"music-acb/{file_name}") or os.path.exists(f"music-wav/{file_name[:-4]}.wav"):
                continue
            url = f"cridata_assets_criaddressables/{path}"
        else:
            continue
        urls.append((url, key_val))

    # 并发下载
    async with requests.AsyncSession() as session:
        tasks = [fetch_resource(session, url, verlist, key) for url, key in urls]
        await asyncio.gather(*tasks)

    print("resource done.")

def pack_zip(info):
    for song in info:
        for index,diff in enumerate(song["diffs"]):
            os.makedirs(f"zip/{diff}", exist_ok=True)

            id = song["id"]
            chart_id = song["chart_id"][index]
            ill_id = song["illustration_id"]
            level_info = song[diff]
            zip_path = f"zip/{diff}/{id}-{level_info["diff"]}.zip"
            with ZipFile(zip_path, "x", compresslevel=9) as zip:
                info_content = {
                    "name": song["name"],
                    "composer": song["composer"],
                    "illustrator": song["illustrator"],
                    "diff": level_info["diff"],
                    "charter": level_info["charter"]
                }
                zip.writestr("info", json.dumps(info_content,ensure_ascii=False))
                zip.write(f"chart/{chart_id}.json", f"{id}.json")
                zip.write(f"illustration-HiRes/{ill_id}.png", f"{id}.png")

async def main():
    # 创建目录
    dir_list = ["chart", "music-wav", "illustration", "illustration-HiRes", "zip", "music-acb", "Unpack_log"]
    for d in dir_list:
        os.makedirs(d, exist_ok=True)

    start_time = time.time()
    print("正在更新rizline数据.")

    async with requests.AsyncSession() as session:
        base_version = await getver_async(session)
        print("base_ver:", base_version)

        # 获取 catalog_catalog.json
        catalog_url = f"{base_version}/Android/catalog_catalog.json"
        catalog_resp = await session.get(catalog_url)
        catalog = catalog_resp.json()

        # 解析 bundle 列表
        temp = base64.b64decode(catalog["m_ExtraDataString"])
        temp = temp.decode(errors='ignore').replace("\u0000", "").replace(
            "LUnity.ResourceManager, Version=0.0.0.0, Culture=neutral, PublicKeyToken=nullJUnityEngine.ResourceManagement.ResourceProviders.AssetBundleRequestOptions",
            ","
        )
        temp = f"[{temp[1:]}]"
        bundle_list = json.loads(temp)
        bundle_list = bundle_list[1:]  # 去掉第一个空元素

        # 获取版本链
        version = base_version.split("/")[-1]
        version_list = []
        bundle_version_dict = {}
        last_version = None
        resp = None
        while True:
            patch_url = f"https://rizlineasset.pigeongames.net/versions/{version}/patch_metadata"
            resp = await session.get(patch_url)
            if resp.status_code > 300:
                version_list.append(version)
                break
            resp.encoding = "utf-8"
            version_bundle = resp.text.split("\n")
            # 记录当前版本
            version_list.append(version)
            # 更新 bundle 映射（上次遍历的版本）
            if last_version:
                for bundle in list(filter(lambda x: x.startswith("Android/"), version_bundle)):
                    bundle = bundle.replace("cridata_assets_criaddressables", "CriAddressables")
                    bundle = bundle.replace("Android/", "")
                    bundle_version_dict[bundle] = last_version
            last_version = version
            version = version_bundle[0] if version_bundle else None
            print(f"fetch_version: {version}")

        bundle_version_dict["verlist"] = version_list
        bundle_version_dict["catalog_catalog.json"] = last_version

        with open("version.json","w",encoding="utf-8") as f:
            json.dump(bundle_version_dict,f,ensure_ascii=False)

        # 下载资源
        await resource_get(catalog, bundle_version_dict)
        print("资源完毕.")

        # 获取信息
        info = await info_get(bundle_list, bundle_version_dict)
        print("info获取完毕.")

        # 打包
        pack_zip(info)
        print("打包完毕.")

    print(f"解包完毕. 用时:{time.time() - start_time:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
