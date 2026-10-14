![Glow Letters — Let the sky write to you.](assets/readme-cover.svg)

# Glow Letters · 霞光来信

Glow Letters turns sunrise and sunset forecasts into a little note about whether to head outside. Sunsethue provides the primary quality forecast; NOAA/NCEP GFS and ECMWF IFS weather are available in expandable details. Optional Windows notifications arrive at 15:00 and 21:00; click one to open the matching view. The interface supports English and 简体中文.

## Connect Sunsethue

Get your personal free API key from the [Sunsethue developer portal](https://sunsethue.com/dev-api), then open **Forecast service → Save and refresh** in the app. The key is encrypted with Windows DPAPI for your Windows account, under `%LOCALAPPDATA%\GlowLetters\sunsethue-key.dat`; it is not included in forecast logs or this repository. For unattended use, `SUNSETHUE_API_KEY` is also supported. The service's free plan is for personal/hobby use, with 1,000 credits per day; each quality-event query uses five credits. Check the provider's current terms before commercial use.

The main card and notification translate Sunsethue's Poor/Fair/Good/Great/Excellent categories into viewing advice. The quality score is **not a probability**, and a good forecast does not guarantee a spectacular sky. Suggested departure times assume a 10-minute walk and arrival 15 minutes before sunrise/sunset; sunrise wake-up advice adds 20 minutes to prepare. These are planning suggestions, not predicted peak-glow times. Golden/blue-hour data, when returned, are retained in the result JSON rather than relabeled as peak glow.

The Chinese presentation conservatively maps those five provider categories to 偏弱 / 一般 / 小烧候选 / 中烧候选 / 大烧候选. These are app display labels, not Sunsethue's original terminology or calibrated burn intensity. If Sunsethue is Good or above but a valid SunsetBot regional model is below its medium-glow threshold, the app flags disagreement and avoids recommending a special trip. The two providers' scores are not numerically comparable.

If Sunsethue is unavailable, fresh valid SunsetBot regional forecasts may provide a clearly named fallback. With no usable quality forecast, the app says it cannot judge; raw weather is never converted into an invented score. `GlowLetters.exe --sunsethue-json result.json --lat 40 --lon 116 --event tomorrow-sunrise` verifies the provider using your locally configured key without opening the app. A missing key produces `not_configured`, not fabricated data. Source: [Sunsethue API](https://sunsethue.com/dev-api), [quality guide](https://sunsethue.com/guide).

Forecast requests send the selected coordinates and the `x-api-key` authentication header directly to Sunsethue over HTTPS. The provider receives these requests; this project runs no intermediary server. You may revoke the key in the provider's portal and remove the local encrypted file to disconnect the service.

**Download:** use the Windows setup wizard attached to the latest GitHub Release. The installer offers optional daily notifications and a desktop shortcut. It does not start with Windows. Open the app, choose a place, and then inspect the forecast.

## Location and forecast areas

“Use my location” asks Windows for an approximate position and shows the returned coordinates and accuracy. Before sending those coordinates to Photon for nearby named OpenStreetMap places, the app asks for consent; you can instead use the coordinate alone. You can choose a building, park, or your current coordinate. “Search places” is available when Windows location or the nearby-places service cannot help. OpenStreetMap coverage varies: a dormitory or classroom can only appear if a map contributor has added it.

The selected place controls the marker and crop on the map. SunsetBot forecasts by its supported city/district name; the app displays that **forecast area separately**. A chosen building is not a building-specific forecast. The crop currently supports coordinates within SunsetBot's East China regional raster (100°–124°E, 17°–42°N); outside it, the app cannot draw a local map crop. It makes the existing image easier to inspect; it does not create a higher-resolution prediction.

## Forecast data and limitations

**Official weather:** the app requests a small GFS region from NOAA NOMADS and selected IFS GRIB records directly from ECMWF's Open Data server. Both use 0.25° grids; the nearest model grid point, distance, run time and valid time are displayed. GFS supplies total/low/mid/high cloud, 2 m humidity, visibility and instantaneous precipitation rate. The IFS subset used here supplies total cloud, 2 m temperature and dew point; unavailable fields remain missing. These are weather forecasts, not an official glow score. GFS uses the nearest hourly step, IFS the nearest three-hourly step; these times can differ from sunrise/sunset and are shown explicitly. Only model runs no more than 30 hours old are accepted, and decoded GRIB times must match the requested run and step. If the latest candidate run is not available, up to four preceding cycles are tried. No old cached forecast is substituted.

**Solar times:** Astral computes sunrise/sunset locally from the selected coordinates, using standard refraction assumptions and an unobstructed horizon. Times are shown in UTC+8. Buildings, terrain, unusual refraction and cloud can change what you actually see; polar days/nights can have no solar crossing. The app does not rely on SunsetBot for solar times or countdowns.

The app queries SunsetBot for today's and tomorrow's sunrise/sunset, separately for GFS and EC. It rejects model/date/city mismatches, stale model runs, and missing quality values. `0.0` is a real zero; missing values remain missing. Solar time is displayed as a single time, not a predicted best-glow interval. SunsetBot intensity and AOD remain separately attributed in details, even when official weather is available. Selecting GFS/EC changes these details and SunsetBot maps; it does not change the Sunsethue conclusion.

SunsetBot and public OpenStreetMap services are independent third-party services. They can be unavailable or change without notice. The official map link remains visible so you can open the original image. The app does not send your position to a server controlled by this project. To look up nearby places, it sends the selected coordinates to Photon (an OpenStreetMap-based service), with Overpass as a fallback; it checks district names with SunsetBot. Configuration and query history stay under your Windows user profile (`%APPDATA%\GlowLetters` and `%LOCALAPPDATA%\GlowLetters`).

## Build from source

Use Python 3.13 on Windows and [Inno Setup 6](https://jrsoftware.org/isinfo.php). In PowerShell, run `./build.ps1`. This installs Python dependencies, builds a PyInstaller app (including ECMWF ecCodes), and creates `release/GlowLetters-0.2.0-Windows-x64-Setup.exe`. GitHub Actions uses the same build on a `v*` tag and attaches the installer to a Release.

To run from source without building, install `requirements.txt` and run `python src/glow_app.py`. `python src/glow_app.py --test-notification` sends one Windows test notification. `python src/sunsetbot.py --city '北京-海淀区' --event tomorrow-sunrise` prints fresh JSON; exit codes 0, 2 and 3 mean full, partial and no valid model forecasts respectively.

`python src/official_weather.py --lat 40 --lon 116 --event all --output official.json` retrieves fresh official GFS/IFS weather for today's sunset and tomorrow's sunrise. Inspect each result's `available`, `run_time`, `valid_time`, `grid`, `http_status` and `fields`; failed attempts remain recorded, and unavailable values are never turned into zero. Official requests send a coordinate bounding box to NOAA; ECMWF receives model-file requests and coordinates are used locally for grid extraction. Data: [NOAA NOMADS](https://nomads.ncep.noaa.gov/) and [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data), the latter under CC BY 4.0. Solar calculations: [Astral](https://astral.readthedocs.io/). Official source outages do not change SunsetBot values, and SunsetBot outages do not prevent local solar calculations or independently returned official forecasts.

The installed app also supports `GlowLetters.exe --official-json official.json --lat 40 --lon 116 --event tomorrow-sunrise`. Omit the coordinates to use the saved location. Both JSON commands return 0 for all models available, 2 for partial availability, and 3 for no usable model forecast. They write a new result, including failures, rather than returning a previous response.

The bundled `city-geo.json` district-coordinate dataset has its own [Mulan PSL v2 license](CITY-GEO-LICENSE.txt). Map and place data are attributed to [OpenStreetMap contributors](https://www.openstreetmap.org/copyright); place data are subject to ODbL. The public [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) limits searches, so the app searches only when you request it. SunsetBot owns its forecasts and maps; this project is unaffiliated with SunsetBot.

Place searches and nearby-place lookups are cached locally to reduce load on public map servers. Operators can switch to other compatible services without rebuilding the app through the `GLOW_NOMINATIM_URL`, `GLOW_PHOTON_URL`, and `GLOW_OVERPASS_URL` environment variables. Large deployments should use a hosted or self-hosted map-data provider rather than relying on public community instances.

## 中文说明

先在 [Sunsethue 开发者页面](https://sunsethue.com/dev-api) 申请个人免费 API Key，再在软件“预报服务”中保存。Key 使用 Windows DPAPI 加密，仅供当前 Windows 账户读取，不进入预报记录或仓库。主界面和消息通知优先给出“值不值得出去看”的建议，NOAA/ECMWF 天气放在“查看依据”里。Sunsethue 的质量评分不是发生概率；出门建议按步行10分钟、日出日落前15分钟到场估算，朝霞再留20分钟准备，不能称为最佳霞光窗口。Sunsethue 不可用时明确标注 SunsetBot 地区预报降级；两个服务都缺报时不编造结论。免费方案用于个人爱好，每日1,000额度，单次质量预报5额度，商用请先查看服务条款。

从 0.2.0 开始，软件直接读取 NOAA/NCEP GFS 和 ECMWF IFS 官方天气数据，并按所选经纬度本地计算日出日落。界面展示官方云量、可用天气字段、起报时间、有效时间以及实际模型网格和距离；官方天气不是火烧云鲜艳度。SunsetBot 的鲜艳度、AOD 和图片仍单独标注来源，互不冒充。GFS 使用最近的小时预报，IFS 使用最近的三小时预报，界面会显示实际有效时间。缺项显示“—”，拒绝超过 30 小时的模型起报；最新候选不可用时尝试前四个周期，不拿旧缓存顶替。日出日落和倒计时不再依赖 SunsetBot，所有时刻仍显示为北京时间；地形、建筑和云雾可能影响实际观测。

霞光来信是一款 Windows 朝霞、晚霞查询软件，提供 SunsetBot 的 GFS 和 EC 数据、官方区域图的本地局部放大，以及可选的每天 15:00 和 21:00 消息通知。点击整条消息通知可打开对应的朝霞或晚霞页面。界面可切换 English / 简体中文。请从 GitHub Release 下载带安装向导的安装包；安装时可以选择定时通知和桌面快捷方式，软件不设置开机自启。

点击“获取位置”后，软件会显示 Windows 返回的经纬度和精度。向 Photon 发送坐标以推荐附近地点前会先征求同意，也可以只使用坐标。附近列表来自 OpenStreetMap 中实际存在的地点；可以选择建筑、公园，或直接使用当前坐标，也可以手动搜索。附近能否出现具体宿舍或教学楼，取决于地图数据库是否收录。选中的地点用于地图标记和裁切；**预报仍来自页面上单独注明的 SunsetBot 地区**，不能把建筑当成精确预报点。目前局部放大只适用于官方“中东”区域图覆盖的东经 100°–124°、北纬 17°–42°；地图放大只是裁切原图，不会提高模型分辨率。

软件分别查询 GFS 和 EC，不把缺报当成 0，也不使用日期、模型或地区不匹配的结果。太阳时刻是单一时刻，不是“最佳霞光时段”；GFS/EC 选择只影响天气详情和 SunsetBot 地图，不改变 Sunsethue 结论。遇到第三方服务不可用时，软件会明确显示缺报或保留官方图片链接。地点和查询历史保存在当前 Windows 用户配置目录；本项目没有自建位置数据服务器。数据与图片版权分别属于原服务及相应贡献者，本项目与预报服务无隶属关系。

开发与打包：Windows + Python 3.13 + Inno Setup 6，运行 `./build.ps1`。源码运行先安装 `requirements.txt`，再执行 `python src/glow_app.py`。
