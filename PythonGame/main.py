import curses
import random

# Screen / map dimensions
SCREEN_W = 80
SCREEN_H = 25
MAP_W = 80
MAP_H = 23          # rows 1-23; row 0 = header, row 24 = message bar
MAP_Y = 1           # map starts at screen row 1

NUM_LEVELS = 3

# Tile glyphs
WALL  = '#'
FLOOR = '.'
STAIR = '>'

# Enemy definitions: (glyph, name, hp, damage, xp_reward)
ENEMY_TYPES = [
    ('g', 'Goblin',   3,  1,  5),
    ('O', 'Orc',      6,  2, 10),
    ('Z', 'Zombie',   5,  1,  8),
    ('V', 'Vampire',  8,  3, 15),
    ('D', 'Dragon',  15,  5, 30),
]


class Entity:
    def __init__(self, x, y, glyph, name, hp, dmg, xp=0):
        self.x, self.y = x, y
        self.glyph = glyph
        self.name = name
        self.hp = hp
        self.max_hp = hp
        self.dmg = dmg
        self.xp = xp
        self.alive = True


class Player(Entity):
    def __init__(self, x, y):
        super().__init__(x, y, '@', 'Player', 20, 3)
        self.xp = 0
        self.dungeon_level = 1


class Room:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def center(self):
        return self.x + self.w // 2, self.y + self.h // 2

    def overlaps(self, other, margin=1):
        return (self.x < other.x + other.w + margin and
                self.x + self.w + margin > other.x and
                self.y < other.y + other.h + margin and
                self.y + self.h + margin > other.y)


class Level:
    def __init__(self, num):
        self.num = num
        self.tiles = [[WALL] * MAP_W for _ in range(MAP_H)]
        self.rooms = []
        self.enemies = []
        self.stair = None
        self._generate()

    # ------------------------------------------------------------------ build
    def _generate(self):
        target = random.randint(6, 10)
        for _ in range(200):
            if len(self.rooms) >= target:
                break
            w = random.randint(5, 13)
            h = random.randint(4, 8)
            x = random.randint(1, MAP_W - w - 2)
            y = random.randint(1, MAP_H - h - 2)
            room = Room(x, y, w, h)
            if any(room.overlaps(r) for r in self.rooms):
                continue
            self._carve_room(room)
            if self.rooms:
                self._connect(self.rooms[-1], room)
            self.rooms.append(room)

        # stairway in last room centre
        cx, cy = self.rooms[-1].center()
        self.stair = (cx, cy)
        self.tiles[cy][cx] = STAIR

        # enemies — scaled per dungeon level
        pool = ENEMY_TYPES[:2] if self.num == 1 else ENEMY_TYPES[:4] if self.num == 2 else ENEMY_TYPES
        for room in self.rooms[1:]:
            for _ in range(random.randint(1, 3)):
                ex = random.randint(room.x + 1, room.x + room.w - 2)
                ey = random.randint(room.y + 1, room.y + room.h - 2)
                if not self._enemy_at(ex, ey):
                    g, name, hp, dmg, xp = random.choice(pool)
                    self.enemies.append(Entity(ex, ey, g, name, hp, dmg, xp))

        # health potions — 4 per level, placed in random rooms
        self.potions = set()
        rooms_for_potions = random.sample(self.rooms, min(len(self.rooms), 4))
        for room in rooms_for_potions:
            px = random.randint(room.x + 1, room.x + room.w - 2)
            py = random.randint(room.y + 1, room.y + room.h - 2)
            if not self._enemy_at(px, py) and (px, py) != self.stair:
                self.potions.add((px, py))

    def _carve_room(self, r):
        for y in range(r.y, r.y + r.h):
            for x in range(r.x, r.x + r.w):
                self.tiles[y][x] = FLOOR

    def _connect(self, a, b):
        ax, ay = a.center()
        bx, by = b.center()
        if random.random() < 0.5:
            self._h_tunnel(min(ax, bx), max(ax, bx), ay)
            self._v_tunnel(min(ay, by), max(ay, by), bx)
        else:
            self._v_tunnel(min(ay, by), max(ay, by), ax)
            self._h_tunnel(min(ax, bx), max(ax, bx), by)

    def _h_tunnel(self, x1, x2, y):
        for x in range(x1, x2 + 1):
            if 0 <= x < MAP_W and 0 <= y < MAP_H:
                self.tiles[y][x] = FLOOR

    def _v_tunnel(self, y1, y2, x):
        for y in range(y1, y2 + 1):
            if 0 <= x < MAP_W and 0 <= y < MAP_H:
                self.tiles[y][x] = FLOOR

    # ------------------------------------------------------------------ query
    def _enemy_at(self, x, y):
        for e in self.enemies:
            if e.alive and e.x == x and e.y == y:
                return e
        return None

    def walkable(self, x, y):
        return 0 <= x < MAP_W and 0 <= y < MAP_H and self.tiles[y][x] != WALL

    def free(self, x, y):
        return self.walkable(x, y) and not self._enemy_at(x, y)


# ====================================================================== Game
class Game:
    def __init__(self, stdscr):
        self.scr = stdscr
        self.msg = "Find the stairs > to descend. Arrow keys to move. Q to quit."
        self.over = False
        self.won = False

        self.levels = [Level(i + 1) for i in range(NUM_LEVELS)]
        sx, sy = self.levels[0].rooms[0].center()
        self.player = Player(sx, sy)
        self.lvl = self.levels[0]

    # ------------------------------------------------------------------ loop
    def run(self):
        curses.curs_set(0)
        self.scr.keypad(True)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE,  -1)  # walls / floor
        curses.init_pair(2, curses.COLOR_GREEN,  -1)  # player
        curses.init_pair(3, curses.COLOR_RED,    -1)  # enemies
        curses.init_pair(4, curses.COLOR_YELLOW, -1)  # stairs / header
        curses.init_pair(5, curses.COLOR_CYAN,   -1)  # message bar
        curses.init_pair(6, curses.COLOR_BLUE,   -1)  # health potion

        while not self.over:
            self._draw()
            self._input()

        self._draw()
        self._end_screen()

    # ------------------------------------------------------------------ draw
    def _draw(self):
        scr = self.scr
        scr.erase()
        p = self.player

        # Header
        header = (f" DUNGEON CRAWLER | Floor {p.dungeon_level}/{NUM_LEVELS}"
                  f" | HP {p.hp}/{p.max_hp} | XP {p.xp} "
                  f"| Enemies: {len(self.lvl.enemies)}")
        scr.addstr(0, 0, header[:SCREEN_W].ljust(SCREEN_W),
                   curses.color_pair(4) | curses.A_BOLD)

        # Map
        for y in range(MAP_H):
            for x in range(MAP_W):
                sy = y + MAP_Y
                tile = self.lvl.tiles[y][x]
                enemy = self.lvl._enemy_at(x, y)

                if x == p.x and y == p.y:
                    attr = curses.color_pair(2) | curses.A_BOLD
                    ch = p.glyph
                elif enemy:
                    attr = curses.color_pair(3)
                    ch = enemy.glyph
                elif (x, y) in self.lvl.potions:
                    attr = curses.color_pair(6) | curses.A_BOLD
                    ch = 'H'
                elif tile == STAIR:
                    attr = curses.color_pair(4) | curses.A_BOLD
                    ch = STAIR
                elif tile == WALL:
                    attr = curses.color_pair(1)
                    ch = WALL
                else:
                    attr = curses.color_pair(1) | curses.A_DIM
                    ch = FLOOR

                try:
                    scr.addch(sy, x, ch, attr)
                except curses.error:
                    pass

        # Message bar
        try:
            scr.addstr(24, 0, (' ' + self.msg)[:SCREEN_W - 1].ljust(SCREEN_W - 1),
                       curses.color_pair(5))
        except curses.error:
            pass

        scr.refresh()

    # ------------------------------------------------------------------ input
    def _input(self):
        key = self.scr.getch()
        dx = dy = 0
        if   key == curses.KEY_UP:    dy = -1
        elif key == curses.KEY_DOWN:  dy =  1
        elif key == curses.KEY_LEFT:  dx = -1
        elif key == curses.KEY_RIGHT: dx =  1
        elif key in (ord('q'), ord('Q')):
            self.over = True
            return
        else:
            return

        nx, ny = self.player.x + dx, self.player.y + dy

        if not self.lvl.walkable(nx, ny):
            return

        enemy = self.lvl._enemy_at(nx, ny)
        if enemy:
            self._attack_enemy(enemy)
        else:
            self.player.x, self.player.y = nx, ny
            if (nx, ny) in self.lvl.potions:
                self._pickup_potion(nx, ny)
            elif (nx, ny) == self.lvl.stair:
                self._descend()

        self._move_enemies()

    # ------------------------------------------------------------------ combat
    def _attack_enemy(self, enemy):
        enemy.hp -= self.player.dmg
        if enemy.hp <= 0:
            enemy.alive = False
            self.lvl.enemies = [e for e in self.lvl.enemies if e.alive]
            self.player.xp += enemy.xp
            self.msg = f"You slew the {enemy.name}! (+{enemy.xp} XP)"
        else:
            self.msg = f"You hit the {enemy.name} for {self.player.dmg} dmg. ({enemy.hp} HP left)"

    def _move_enemies(self):
        p = self.player
        for e in list(self.lvl.enemies):
            if not e.alive:
                continue
            dx = p.x - e.x
            dy = p.y - e.y
            dist = abs(dx) + abs(dy)

            if dist == 1:
                p.hp -= e.dmg
                self.msg = f"The {e.name} hits you for {e.dmg} dmg! ({p.hp} HP left)"
                if p.hp <= 0:
                    self.over = True
                    self.won = False
                    return
            elif dist <= 10:
                mx = (1 if dx > 0 else -1) if dx != 0 else 0
                my = (1 if dy > 0 else -1) if dy != 0 else 0
                # prefer axis with greater distance
                if abs(dx) >= abs(dy):
                    step = [(mx, 0), (0, my)]
                else:
                    step = [(0, my), (mx, 0)]
                for sx, sy in step:
                    nx, ny = e.x + sx, e.y + sy
                    if (self.lvl.free(nx, ny) and
                            not (nx == p.x and ny == p.y)):
                        e.x, e.y = nx, ny
                        break
            else:
                if random.random() < 0.2:
                    sx = random.choice([-1, 0, 0, 1])
                    sy = random.choice([-1, 0, 0, 1])
                    nx, ny = e.x + sx, e.y + sy
                    if self.lvl.free(nx, ny):
                        e.x, e.y = nx, ny

    # ------------------------------------------------------------------ items
    def _pickup_potion(self, x, y):
        self.lvl.potions.discard((x, y))
        self.player.hp = self.player.max_hp
        self.msg = f"You drink a health potion and are fully healed! ({self.player.hp}/{self.player.max_hp})"

    # ------------------------------------------------------------------ level
    def _descend(self):
        if self.player.dungeon_level >= NUM_LEVELS:
            self.over = True
            self.won = True
            self.msg = "You escaped the dungeon!  YOU WIN!"
        else:
            self.player.dungeon_level += 1
            self.lvl = self.levels[self.player.dungeon_level - 1]
            sx, sy = self.lvl.rooms[0].center()
            self.player.x, self.player.y = sx, sy
            self.msg = f"You descend to floor {self.player.dungeon_level}..."

    # ------------------------------------------------------------------ end
    def _end_screen(self):
        self.scr.erase()
        if self.won:
            lines = [
                "*** YOU ESCAPED THE DUNGEON ***",
                "",
                f"XP collected: {self.player.xp}",
                f"HP remaining: {self.player.hp}/{self.player.max_hp}",
            ]
        else:
            lines = [
                "*** YOU HAVE DIED ***",
                "",
                f"Floor reached: {self.player.dungeon_level}/{NUM_LEVELS}",
                f"XP collected:  {self.player.xp}",
            ]
        lines += ["", "Press any key to exit."]
        start_y = (SCREEN_H - len(lines)) // 2
        for i, line in enumerate(lines):
            x = max(0, (SCREEN_W - len(line)) // 2)
            try:
                self.scr.addstr(start_y + i, x, line,
                                curses.color_pair(4) | curses.A_BOLD)
            except curses.error:
                pass
        self.scr.refresh()
        self.scr.getch()


# ======================================================================= main
def main():
    curses.wrapper(lambda s: Game(s).run())


if __name__ == '__main__':
    main()
