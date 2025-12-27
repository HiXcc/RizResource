# RizResource
本项目依赖[Vgmstream](https://github.com/vgmstream/vgmstream)

# 实现原理
###### 我个人的语言表达和术语积累不是很多,表达有不清晰/术语使用错误见谅
以下内容若无特殊说明,则请求头无要求(你甚至可以演都不演直接开爬💦).  
## 获取catalog.json
Rizline在进入游戏时会有"检查更新"的过程,该过程将会先发出get请求
```
请求头:{"game_id":"pigeongames.rizline"}
https://rizserver.pigeongames.net/game/server_api/v1/dis
```
返回如以下示例的json文件:
```
{"configs":[{"version":"2.0.9",
"resourceUrl":"https://rizlineasset.pigeongames.net/versions/v109_2_0_9_523d8dd4e0P",
"resourceBaseUrl":"https://rizlineasset.pigeongames.net/versions",
"resourceVersion":"v109_2_0_9_523d8dd4e0P"}],
"minimalVersion":"2.0.9"}
```
以"resourceVersion"作为⌈version⌋,向
```
https://rizlineasset.pigeongames.net/versions/{version}/patch_metadata
```
发出请求,此时有两种返回:
#### 第一种
```
v100_2_0_8_86e2fda4e0
......
Android/catalog_catalog.hash
Android/catalog_catalog.json
......
iOS/catalog_catalog.hash
iOS/catalog_catalog.json
......
```
此时将以返回值第一行的版本号(如上即v100_2_0_8_86e2fda4e0)作为新的⌈version⌋进行请求.
#### 第二种
```
<?xml version="1.0" encoding="UTF-8"?>
<Error>
  <Code>NoSuchKey</Code>
  <Message>The specified key does not exist.</Message>
  <RequestId>694792201C0FF73933163CFC</RequestId>
  <HostId>rizlineassetstore.oss-cn-hongkong.aliyuncs.com</HostId>
  <Key>versions/v100_2_0_8_86e2fda4e0/patch_metadata</Key>
  <EC>0026-00000001</EC>
  <RecommendDoc>https://api.aliyun.com/troubleshoot?q=0026-00000001</RecommendDoc>
</Error>
```
这意味着此时的⌈version⌋为最新的版本号,此时可以向
```
https://rizlineasset.pigeongames.net/versions/{version}/Android/catalog_catalog.json
```
发出请求,获取最新的catalog.json.

## 获取具体资源
*Rizline的catalog.json与Phigros的结构类似,但额外多出"m_ExtraDataString",且资产标识头有所不同.  
Phigros的catalog.json见[Phigros_Resource](https://github.com/7aGiven/Phigros_Resource/)  
key/bucket/entry用于获取在游戏内的所有曲绘/音乐/谱面
标识头
- 谱面:chart
- 曲绘:illustration(*曲绘中还有一种类型:HiRes,但其指向的bundle并不适用于常规的url.)
- 音乐应当含有:"CriAddressables/"
资产所在url:
```
https://rizlineasset.pigeongames.net/versions/{ver}/Android/{entry}
```
音乐于服务器上的格式为.acb,应当进行转换.  
  
m_ExtraDataString本质上是一个掺入部分unity/乱码元素的json(经base64加密)  
可将以下字符串视为分割符:
```
LUnity.ResourceManager, Version=0.0.0.0, Culture=neutral, PublicKeyToken=nullJUnityEngine.ResourceManagement.ResourceProviders.AssetBundleRequestOptions
```
其内部元素bundle为进入游戏热更新的内容;  
bundle所在url:
```
https://rizlineasset.pigeongames.net/versions/{ver}/Android/{"m_Hash"}.bundle
```
*定数/曲目信息于这些bundle其中的一个资产,名称为:Default;类型为:MonoBehaviour  

# 无聊琐事
某些时间rizline的服务器ssl证书可能会掉.导致无法正常登录与下载资源  
因此在更新时可考虑绕过SSL证书验证(反正就我一个人用(逃

# SpecialThanks:
- [咕的岛鸽](https://space.bilibili.com/521730845)
- [Phigros_Resource](https://github.com/7aGiven/Phigros_Resource/)
