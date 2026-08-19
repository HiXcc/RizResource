import base64
import UnityPy
import os
import json
from acbtoogg import convert_acb_to_ogg
import asyncio
from curl_cffi import requests

header = {
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0"
}

class ByteReader:
    def __init__(self, data):
        self.data = data
        self.position = 0

    def readInt(self):
        self.position += 4
        return self.data[self.position - 4] ^ self.data[self.position - 3] << 8 ^ self.data[self.position - 2] << 16

def get_info(list,id) -> dict:
    for dict in list:
        if dict["id"] == id:
            return dict
    return -1

def safe_string(string):
    try:
        string.encode("gbk")
        return True
    except UnicodeEncodeError:
        return False

def color_convert(color):
    return (round(color["r"]*255),round(color["g"]*255),round(color["b"]*255),round(color["a"]*255))

def getver():
    """返回示例:https://rizlineasset.pigeongames.net/versions/v109_2_0_9_523d8dd4e0P"""
    headers = {"game_id":"pigeongames.rizline"}
    ver = requests.get("https://rizserver.pigeongames.net/game/server_api/v1/dis",headers=headers,verify=False)
    print(ver)
    return ver.json()["configs"][0]["resourceUrl"]

async def fetch(session:requests.AsyncSession, url):
    resp = await session.get(url,headers=header,impersonate="chrome120",timeout=600)
    if resp.status_code < 300:
        bundle = resp.content
        env = UnityPy.load(bundle)  # 加载bundle文件
        for obj in env.objects:  # 遍历所有bundle的所有资源
            data = obj.read()
            if hasattr(data,"m_Name"):
                if data.m_Name == "Default":
                    d = obj.read_typetree()
                    if "m_GameObject" in d:
                        return d
                if data.m_Name == "zh-Hans.bio":
                    with open(f"{data.m_Name}.txt","wb") as tf:
                        tf.write(data.m_Script.encode())
                if data.m_Name == "zh-Hans.achievement":
                    with open(f"{data.m_Name}.txt","wb") as tf:
                        tf.write(data.m_Script.encode())
                if data.m_Name == "zh-Hans.weeklyTask":
                    with open(f"{data.m_Name}.txt","wb") as tf:
                        tf.write(data.m_Script.encode())
    else:
        print(url,resp.status_code)
    return False

async def info_get(bundle_list:list,ver:dict):
    for bundle in bundle_list:
        if bundle["m_BundleName"] == "bc06b7df85213f57979af8925a2d787a":
            info_bundle = f"{bundle["m_Hash"]}.bundle"
        if bundle["m_BundleName"] == "082fc974cd54ee688f9245a33ac24459":
            bio_bundle = f"{bundle["m_Hash"]}.bundle"
        if bundle["m_BundleName"] == "27f38416a97358ea81fae5408729ff53":
            weekly_bundle = f"{bundle["m_Hash"]}.bundle"
        if bundle["m_BundleName"] == "913a07462eb62aace70586d300a841eb":
            achievement_bundle = f"{bundle["m_Hash"]}.bundle"
    base_v = ver["base_v"]
    urls = [f"https://rizlineasset.pigeongames.net/versions/{ver.get(info_bundle,base_v)}/Android/{info_bundle}",
            f"https://rizlineasset.pigeongames.net/versions/{ver.get(bio_bundle,base_v)}/Android/{bio_bundle}",
            f"https://rizlineasset.pigeongames.net/versions/{ver.get(weekly_bundle,base_v)}/Android/{weekly_bundle}",
            f"https://rizlineasset.pigeongames.net/versions/{ver.get(achievement_bundle,base_v)}/Android/{achievement_bundle}"]
    
    async with requests.AsyncSession() as session:
        tasks = [fetch(session, url) for url in urls]
        bundle_list = await asyncio.gather(*tasks)
    d = list(filter(lambda x:x,bundle_list))[0]
    
    infos = []
    for song in d["levels"] + d["discOLevels"]:
        id = song["id"]
        music_id:str = song["musicId"]
        ill_id = song["illustrationId"]
        chart_id = song["chartIds"]
        music_dict = get_info(d["musics"],music_id)
        ill_dict = get_info(d["illustrations"],ill_id)
        info = {"id":id,
                "chart_id":chart_id,
                "music_id":music_id,
                "illustration_id":ill_id,
                "chap":song["discName"],
                "name":music_dict["musicName"],
                "composer":music_dict["artist"],
                "themeUiColor":color_convert(music_dict["themeUiColor"]),
                "pst":music_dict["previewStartTime"],
                "pet":music_dict["previewOverTime"],
                "illustrator":ill_dict["artist"],}
        diff_list = []
        for chart in chart_id:
            chart_dict = get_info(d["charts"],chart)
            info.update({chart_dict["level"]:{"diff":round(chart_dict["difficulty"],1),
                                        "charter":chart_dict["designer"],}})
            diff_list.append(chart_dict["level"])
        info["diffs"] = diff_list
        infos.append(info)

    with open("info.json","w",encoding="utf-8") as default_mono:
        json.dump(infos,default_mono,ensure_ascii=False)
    with open("layout.json","w",encoding="utf-8") as default_mono:
        json.dump(d["layoutColors"],default_mono,ensure_ascii=False)
    with open("diffcolors.json","w",encoding="utf-8") as default_mono:
        json.dump(d["difficultyColors"],default_mono,ensure_ascii=False)
    with open("default_raw.json","w",encoding="utf-8") as default_mono:
        json.dump(d,default_mono,ensure_ascii=False)

    print("info done.")
    return infos

def resource_get(data,verlist):
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
        
    for i in range(len(table)):
        if table[i][1] != 65535:
            table[i][1] = table[table[i][1]][0]

    Resource = []
    extra = []

    for i in range(len(table) - 1, -1, -1):
        if type(table[i][0]) != str or type(table[i][1]) != str:
            del table[i]
            continue
        if table[i][0][:5] == "chart":
            Resource.append(table[i])
        elif table[i][0].startswith(("illustration","altIllustration")):
            # 后缀HiRes是高清曲绘.
            Resource.append(table[i])
        elif table[i][0][:16] == "CriAddressables/":
            Resource.append(table[i])
        else:
            extra.append(table[i])
    
    with open("Unpack_log/all_resource","w",encoding="utf-8") as f:
        for i in range(len(Resource)):
            f.write(str(Resource[i])+"\n")  # 记录所有符合的资源
        for i in range(len(extra)):
            f.write(str(extra[i])+"\n")

    with open("Unpack_log/chart_log","w",encoding="utf-8") as f:
        for i in range(len(Resource)):
            if Resource[i][0].startswith("chart"):
                f.write(str(Resource[i])+"\n")  # 记录所有符合的谱面资源
    
    with open("Unpack_log/illustration_log","w",encoding="utf-8") as f:
        for i in range(len(Resource)):
            if Resource[i][0].startswith(("illustration","altIllustration")):
                f.write(str(Resource[i])+"\n")  # 记录所有符合的曲绘资源
    
    with open("Unpack_log/music_log","w",encoding="utf-8") as f:
        for i in range(len(Resource)):
            if Resource[i][0].startswith("CriAddressables/"):
                f.write(str(Resource[i])+"\n")  # 记录所有符合的音乐资源

    # 谱面示例:['chart.CrazyAudiophile.Supa7onyz.0.IN', '12523ede2bc20dcc4a7822bdd566d2ee.bundle']
    # 音频示例:['CriAddressables/onandon.etia.0.acb=367a00', 'cridata_assets_criaddressables/onandon.etia.0.acb=367a00_7befa38d3fd5cd186b258db5e6641db1.bundle']
    # 曲绘示例:['illustration.SwingSweetTweeDance.Uske.0.HiRes', '403502c402c4be614dd148d6c1738d31.bundle']
    # bundle文件内含有该谱面

    for key, entry in Resource:
        key:str;entry:str
        if key in verlist:
            ver = verlist[key]
        elif entry in verlist:
            ver = verlist[entry]
        else:
            ver = verlist["catalog_catalog.json"]

        if key.startswith(("chart","illustration","altIllustration")):
            if os.path.exists(f"chart/{key}.json"):
                continue
            if os.path.exists(f"illustration-HiRes/{key.removesuffix(".HiRes")}.png"):
                continue
            if os.path.exists(f"illustration/{key.removesuffix(".HiRes")}.png"):
                continue
            url = f"https://rizlineasset.pigeongames.net/versions/{ver}/Android/{entry}"
        elif key.startswith("CriAddressables/") and not entry.startswith("crilocaldata_assets_all"):
            path = key.removeprefix("CriAddressables/")
            file_name = path[:-7]
            if not safe_string(file_name):
                file_name = file_name.encode("gbk",errors="ignore").decode("utf-8")
            if os.path.exists(f"music-mp3/{file_name[:-4]}.wav"):
                continue
            if os.path.exists(f"music-acb/{file_name}"):
                continue
            url = f"https://rizlineasset.pigeongames.net/versions/{ver}/Android/cridata_assets_criaddressables/{path}"
        else:
            continue

        for ver in verlist["verlist"]:
            bundle = requests.get(url,headers=header,timeout=600)
            if bundle.status_code <= 300:
                break
        if key.startswith("CriAddressables/") and not entry.startswith("crilocaldata_assets_all"):
            path = key.removeprefix("CriAddressables/")
            file_name = path[:-7]
            if not safe_string(file_name):
                file_name = file_name.encode("gbk",errors="ignore").decode("utf-8")
            with open(f"music-acb/{file_name}","wb") as m:
                m.write(bundle.content)
        else:
            env = UnityPy.load(bundle.content)  # 加载bundle文件
            for obj in env.objects:  # 遍历所有bundle的所有资源
                data = obj.read()
                if obj.type.name == "TextAsset":  # 若为文字资源
                    content = data.m_Script.encode()
                    with open(f"chart/{key}.json", "wb") as f:
                        f.write(content)
                elif obj.type.name == "Texture2D":
                    if key.endswith("HiRes"):
                        data.image.save(f"illustration-HiRes/{key.removesuffix(".HiRes")}.png")
                    else:
                        data.image.save(f"illustration/{key}.png")

    for music_acb in os.listdir("music-acb/"):
        if not safe_string(music_acb):
            music_acb = music_acb.encode("gbk",errors="ignore").decode("utf-8")
        if not convert_acb_to_ogg(f"music-acb/{music_acb}", "music-wav"):
            print(f"error:{music_acb}")

    print("resource done.")

async def main():
    dir_list = ["chart","music-wav","illustration","illustration-HiRes","zip","music-acb","Unpack_log/"]
    for dir in dir_list:
        os.makedirs(dir,exist_ok=True)

    print("正在更新rizline数据.")
    base_version:str = getver()
    print("ver:",base_version)
    url = f"{base_version}/Android/catalog_catalog.json"
    catalog = requests.get(f"{base_version}/Android/catalog_catalog.json").json()
    temp = base64.b64decode(catalog["m_ExtraDataString"]).decode(errors='ignore').replace("\u0000","").split("LUnity.ResourceManager, Version=0.0.0.0, Culture=neutral, PublicKeyToken=nullJUnityEngine.ResourceManagement.ResourceProviders.AssetBundleRequestOptions")
    bundle_list = temp[1:]
    false = False
    true = True
    NULL = None
    for i,item in enumerate(bundle_list):
        bundle_list[i] = eval(item)
    base_version = base_version.split("/")[-1]
    version_list = [base_version]
    version = base_version
    version_bundle = ["",""]
    bundle_version_dict = {}
    while not version.startswith("<?xml"):
        #https://rizlineasset.pigeongames.net/versions/v101_2_0_9_fed974f1d6P/patch_metadata
        url = f"https://rizlineasset.pigeongames.net/versions/{version}/patch_metadata"
        for bundle in  version_bundle[1:]:
            if bundle.startswith("Android/"):
                bundle = bundle.replace("cridata_assets_criaddressables","CriAddressables")
                bundle = bundle.replace("Android/","")
                bundle_version_dict.update({bundle:last_version})
        response = requests.get(url)
        response.encoding = "utf-8"
        version_bundle = response.text.split("\n")

        last_version = version
        version_list.append(last_version)
        version = version_bundle[0]
        bundle_version_dict.update({"base_v":base_version})

    bundle_version_dict.update({"verlist":version_list})
    bundle_version_dict.update({"catalog_catalog.json":last_version})
    #https://rizlineasset.pigeongames.net/versions/v100_2_0_8_86e2fda4e0/Android/catalog_catalog.json
    resource_get(catalog,bundle_version_dict)
    print("资源完毕.")
    
    await info_get(bundle_list,bundle_version_dict)
    print("info获取完毕.")

if __name__ == "__main__":
    asyncio.run(main())
