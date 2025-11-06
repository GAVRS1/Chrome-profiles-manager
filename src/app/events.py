from dataclasses import dataclass

@dataclass
class MouseClick:
    button: str  # 'left' | 'right' | 'middle'
    x: int       # экранные координаты
    y: int

@dataclass
class MouseWheel:
    delta: int   # кратно 120
    x: int
    y: int

@dataclass
class KeyEvent:
    vk: int      # виртуальный код
    is_down: bool
    char: str | None = None
