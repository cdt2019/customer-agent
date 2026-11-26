"""后台任务的开关。同步、建索引和评测同一时间只跑一个，所以一个「停止」信号就够。"""

from threading import Event, Lock

maintenance = Lock()  # 同步和建索引会改块、占显卡
stop = Event()  # 任务每做完一篇或一题看一眼，亮了就停
