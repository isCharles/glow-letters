# Glow Letters · 霞光来信

Glow Letters is a small Windows app for checking SunsetBot sunrise and sunset glow forecasts. It shows the live GFS and EC values, Windows notifications at 15:00 and 21:00 if you opt in, and a local crop of SunsetBot's official regional map. The interface can be switched between English and 简体中文.

**Download:** use the Windows setup wizard attached to the latest GitHub Release. The installer offers optional daily notifications and a desktop shortcut. It does not start with Windows. Open the app, choose a place, and then inspect the forecast.

## Location and forecast areas

“Use my location” asks Windows for an approximate position and shows the returned coordinates and accuracy. Before sending those coordinates to Photon for nearby named OpenStreetMap places, the app asks for consent; you can instead use the coordinate alone. You can choose a building, park, or your current coordinate. “Search places” is available when Windows location or the nearby-places service cannot help. OpenStreetMap coverage varies: a dormitory or classroom can only appear if a map contributor has added it.

The selected place controls the marker and crop on the map. SunsetBot forecasts by its supported city/district name; the app displays that **forecast area separately**. A chosen building is not a building-specific forecast. The crop currently supports coordinates within SunsetBot's East China regional raster (100°–124°E, 17°–42°N); outside it, the app cannot draw a local map crop. It makes the existing image easier to inspect; it does not create a higher-resolution prediction.

## Forecast data and limitations

The app queries SunsetBot for today's and tomorrow's sunrise/sunset, separately for GFS and EC. It rejects model/date/city mismatches, stale model runs, and missing quality values. `0.0` is a real zero; missing values remain missing. The displayed time interval is a fixed window around the reported sunrise or sunset time, **not** a predicted best-glow interval. AOD is shown exactly as reported by SunsetBot.

SunsetBot and public OpenStreetMap services are independent third-party services. They can be unavailable or change without notice. The official map link remains visible so you can open the original image. The app does not send your position to a server controlled by this project. To look up nearby places, it sends the selected coordinates to Photon (an OpenStreetMap-based service), with Overpass as a fallback; it checks district names with SunsetBot. Configuration and query history stay under your Windows user profile (`%APPDATA%\GlowLetters` and `%LOCALAPPDATA%\GlowLetters`).

## Build from source

Use Python 3.13 on Windows and [Inno Setup 6](https://jrsoftware.org/isinfo.php). In PowerShell, run `./build.ps1`. This installs Python dependencies, builds a PyInstaller app, and creates `release/GlowLetters-0.1.0-Windows-x64-Setup.exe`. GitHub Actions uses the same build on a `v*` tag and attaches the installer to a Release.

To run from source without building, install `requirements.txt` and run `python src/glow_app.py`. `python src/glow_app.py --test-notification` sends one Windows test notification. `python src/sunsetbot.py --city '北京-海淀区' --event tomorrow-sunrise` prints fresh JSON; exit codes 0, 2 and 3 mean full, partial and no valid model forecasts respectively.

The bundled `city-geo.json` district-coordinate dataset has its own [Mulan PSL v2 license](CITY-GEO-LICENSE.txt). Map and place data are attributed to [OpenStreetMap contributors](https://www.openstreetmap.org/copyright); place data are subject to ODbL. The public [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) limits searches, so the app searches only when you request it. SunsetBot owns its forecasts and maps; this project is unaffiliated with SunsetBot.

Place searches and nearby-place lookups are cached locally to reduce load on public map servers. Operators can switch to other compatible services without rebuilding the app through the `GLOW_NOMINATIM_URL`, `GLOW_PHOTON_URL`, and `GLOW_OVERPASS_URL` environment variables. Large deployments should use a hosted or self-hosted map-data provider rather than relying on public community instances.

## 中文说明

霞光来信是一款 Windows 朝霞、晚霞查询软件，提供 SunsetBot 的 GFS 和 EC 数据、官方区域图的本地局部放大，以及可选的每天 15:00 和 21:00 消息通知。界面可切换 English / 简体中文。请从 GitHub Release 下载带安装向导的安装包；安装时可以选择定时通知和桌面快捷方式，软件不设置开机自启。

点击“获取位置”后，软件会显示 Windows 返回的经纬度和精度。向 Photon 发送坐标以推荐附近地点前会先征求同意，也可以只使用坐标。附近列表来自 OpenStreetMap 中实际存在的地点；可以选择建筑、公园，或直接使用当前坐标，也可以手动搜索。附近能否出现具体宿舍或教学楼，取决于地图数据库是否收录。选中的地点用于地图标记和裁切；**预报仍来自页面上单独注明的 SunsetBot 地区**，不能把建筑当成精确预报点。目前局部放大只适用于官方“中东”区域图覆盖的东经 100°–124°、北纬 17°–42°；地图放大只是裁切原图，不会提高模型分辨率。

软件分别查询 GFS 和 EC，不把缺报当成 0，也不使用日期、模型或地区不匹配的结果。显示的时间区间是围绕日出日落时刻的固定窗口，不是“最佳霞光时段”。遇到第三方服务不可用时，软件会明确显示缺报或保留官方图片链接。地点和查询历史保存在当前 Windows 用户配置目录；本项目没有自建位置数据服务器。数据与图片版权分别属于 SunsetBot、OpenStreetMap 及相应贡献者，本项目与 SunsetBot 无隶属关系。

开发与打包：Windows + Python 3.13 + Inno Setup 6，运行 `./build.ps1`。源码运行先安装 `requirements.txt`，再执行 `python src/glow_app.py`。
