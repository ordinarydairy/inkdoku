from machine import Pin
import time
from datetime import timedelta
import random
from epaper42 import EPD
import keypad


KEY_MAP = [
    "S", "U", "1", "2", "3",
    "L", "R", "4", "5", "6",
    "",  "D", "7", "8", "9",
    "",  "P", "M", "N", "J"
]

# pin assignments = GPX and not physical pins

km = keypad.KeyMatrix(
    row_pins=(
        Pin(0,  Pin.IN, Pin.PULL_UP),
        Pin(1,  Pin.IN, Pin.PULL_UP), 
        Pin(2,  Pin.IN, Pin.PULL_UP), 
        Pin(3,  Pin.IN, Pin.PULL_UP)),
    column_pins=(
        Pin(4,  Pin.IN, Pin.PULL_UP), 
        Pin(5,  Pin.IN, Pin.PULL_UP), 
        Pin(6,  Pin.IN, Pin.PULL_UP), 
        Pin(7,  Pin.IN, Pin.PULL_UP),
        Pin(8,  Pin.IN, Pin.PULL_UP)),
    columns_to_anodes=True,
)


#pixel font, each comma seperated thingy = new row, 0/1 = black/white

FONT5x7 = {
    '0': [0b01110, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b01110, 0b01010],
    '1': [0b00100, 0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    '2': [0b01110, 0b10001, 0b10001, 0b00001, 0b00010, 0b00100, 0b01000, 0b10000, 0b11111],
    '3': [0b01110, 0b10001, 0b00001, 0b00110, 0b00001, 0b00001, 0b00001, 0b10001, 0b01110],
    '4': [0b00010, 0b00110, 0b01010, 0b10010, 0b10010, 0b10010, 0b11111, 0b00010, 0b00111],
    '5': [0b11111, 0b10000, 0b10000, 0b11110, 0b00001, 0b00001, 0b10001, 0b10001, 0b01110],
    '6': [0b01110, 0b10001, 0b10000, 0b10110, 0b11001, 0b10001, 0b10001, 0b10001, 0b01110],
    '7': [0b11111, 0b10001, 0b00010, 0b00010, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100],
    '8': [0b01110, 0b10001, 0b10001, 0b10001, 0b01110, 0b10001, 0b10001, 0b10001, 0b01110],
    '9': [0b01110, 0b10001, 0b10001, 0b10001, 0b10011, 0b01101, 0b00001, 0b10001, 0b01110],
}

def draw_digit(fb, digit, x, y, scale=2, color=0):
    """Draw a digit at pixel (x,y) with given scale. color 0=black 1=white."""
    rows = FONT5x7[str(digit)]
    for row_i, row_bits in enumerate(rows):
        for col_i in range(5):
            if row_bits & (0b10000 >> col_i):
                for dy in range(scale):
                    for dx in range(scale):
                        fb.pixel(x + col_i*scale + dx,
                                 y + row_i*scale + dy, color)


# Layout constants 

GRID_LEFT   = 65      # left margin for grid
GRID_TOP    = 7      # top margin
CELL_SIZE   = 30      # pixels per cell  
BOX_THICK   = 2       # thick line for 3x3 box borders
CELL_THICK  = 1       # thin line for cell borders
DIGIT_SCALE = 2      # font scale: 3 => 15x21 px digit inside 36px cell
DIGIT_OFF_X = (CELL_SIZE - 5*DIGIT_SCALE) // 2   # center digit in cell
DIGIT_OFF_Y = (CELL_SIZE - 7*DIGIT_SCALE) // 2 - 1

JOT_SCALE = 1

STATUS_Y    = GRID_TOP + 9*CELL_SIZE + 6   # status text row

# puzzle generator / solver 

def _possible(board, row, col, num):
    if num in board[row]:
        return False
    if num in [board[r][col] for r in range(9)]:
        return False
    br, bc = (row // 3)*3, (col // 3)*3
    for r in range(br, br+3):
        for c in range(bc, bc+3):
            if board[r][c] == num:
                return False
    return True

def _solve(board, limit=2):
    """Return list of up to `limit` solutions (stops early)."""
    solutions = []
    def bt():
        if len(solutions) >= limit:
            return
        for r in range(9):
            for c in range(9):
                if board[r][c] == 0:
                    nums = list(range(1, 10))
                    random.shuffle(nums)
                    for n in nums:
                        if _possible(board, r, c, n):
                            board[r][c] = n
                            bt()
                            if len(solutions) >= limit:
                                return
                            board[r][c] = 0
                    return
        solutions.append([row[:] for row in board])
    bt()
    return solutions

def generate_puzzle(clues=35):
    """Generate a Sudoku puzzle with ~clues given cells."""
    # Build a filled board
    board = [[0]*9 for _ in range(9)]
    sols = _solve(board, limit=1)
    if not sols:
        return None, None
    solution = sols[0]

    # Remove cells while puzzle remains uniquely solvable
    puzzle = [row[:] for row in solution]
    positions = [(r, c) for r in range(9) for c in range(9)]
    random.shuffle(positions)
    removed = 0
    target_remove = 81 - clues
    for r, c in positions:
        if removed >= target_remove:
            break
        val = puzzle[r][c]
        puzzle[r][c] = 0
        test = [row[:] for row in puzzle]
        if len(_solve(test, limit=2)) == 1:
            removed += 1
        else:
            puzzle[r][c] = val  # restore

    return puzzle, solution

# Game state

class SudokuGame:
    def __init__(self):
        self.puzzle   = None   # original clues (0 = empty)
        self.solution = None
        self.board    = None 
        self.candidates = None  
        self.cursor_r = 0
        self.cursor_c = 0
        self.solved    = False
        self.errors    = 0
        self.menu_open = False
        self.pencil = False
        self.menuy = 0
        self.new_game()

    def new_game(self, clues=20):
        self.puzzle, self.solution = generate_puzzle(clues)
        self.board = [row[:] for row in self.puzzle]
        self.candidates = [[set() for _ in range(9)] for _ in range(9)]
        self.cursor_r = 0
        self.cursor_c = 0
        self.solved = False
        self.errors = 0
        self.start_time = time.time()
        self.elapsed_time = 0
        self.menuy = 0
        self.pencil = False
        self.undo_stack = []

    def restart_game(self):
        self.board = [row[:] for row in self.puzzle]
        self.candidates = [[set() for _ in range(9)] for _ in range(9)]
        self.cursor_r = 0
        self.cursor_c = 0
        self.solved = False
        self.errors = 0
        self.start_time = time.time()
        self.elapsed_time = 0
        self.menuy = 0
        self.pencil = False
        self.undo_stack = []



    def is_clue(self, r, c):
        return self.puzzle[r][c] != 0

    def move(self, dr, dc):
            self.cursor_r = (self.cursor_r + dr) % 9
            self.cursor_c = (self.cursor_c + dc) % 9

    def menumove(self, menupos):
        self.menuy = (self.menuy + menupos) % 3
        print(self.menuy)

    def input(self, num):

        r, c = self.cursor_r, self.cursor_c
        if self.is_clue(r, c) or self.solved:
            return
        val = self.board[r][c]
        placing = (num != 0 and val != num)
        was_error = placing and num != self.solution[r][c]

        # Snapshot candidates for affected cells before any change
        affected = {(r, c)}
        if placing:
            for pr, pc in self.peers(r, c):
                affected.add((pr, pc))
        saved_cands = {pos: frozenset(self.candidates[pos[0]][pos[1]]) for pos in affected}
        self.undo_stack.append(('input', r, c, val, was_error, saved_cands))
        if len(self.undo_stack) > 20:
            self.undo_stack.pop(0)

        self.board[r][c] = num
        print(f"pressing {num}")
        if val == num: #clearing the cell
            self.board[r][c] = 0
        elif was_error: # adding to error count
            self.errors += 1

        self.candidates[r][c].clear() # clearing own pencil marks

        if self.board[r][c] != 0:
            for pr, pc in self.peers(r, c):
                self.candidates[pr][pc].discard(num)

        # Check win
        if all(self.board[r][c] == self.solution[r][c]
               for r in range(9) for c in range(9)):
            self.solved = True
    def peers(self, r, c): # finding every cell that shares a box/line with this cell
        for cc in range(9):
            if cc != c:
                yield r, cc
        for rr in range(9):
            if rr !=r:
                yield rr, c
        br, bc = (r//3) * 3, (c//3) * 3
        for rr in range(br,br+3):
            for cc in range (bc,bc+3):
                yield rr,cc

    def jot(self, jnum):
        r, c = self.cursor_r, self.cursor_c
        if self.is_clue(r, c) or self.solved or self.board[r][c] != 0:
            return

        self.undo_stack.append(('jot', r, c, frozenset(self.candidates[r][c])))
        if len(self.undo_stack) > 20:
            self.undo_stack.pop(0)

        cell = self.candidates[r][c]
        if jnum in cell:
            cell.discard(jnum)
            print(f"removing jot {jnum}")
        else:
            cell.add(jnum)
            print(f"jotting down {jnum}")
            

    def undo(self):
        if not self.undo_stack:
            return
        entry = self.undo_stack.pop()
        if entry[0] == 'input':
            _, r, c, old_val, was_error, saved_cands = entry
            if was_error:
                self.errors = max(0, self.errors - 1)
            self.board[r][c] = old_val
            self.solved = False
            self.cursor_r, self.cursor_c = r, c
            for (pr, pc), cands in saved_cands.items():
                self.candidates[pr][pc] = set(cands)
        elif entry[0] == 'jot':
            _, r, c, old_cands = entry
            self.candidates[r][c] = set(old_cands)
            self.cursor_r, self.cursor_c = r, c

    # menu goals for now: start a new game with difficulty, reset game?, functions as pause menu, exit menu button
    def menuselect(self):
        if self.menuy == 0:
            print("New Game")
            self.new_game()
            self.menu_open = False
        elif self.menuy == 1:
            print("Restarting Game")
            self.restart_game()
            self.menu_open = False
        elif self.menuy == 2:
            print("Closing Menu")
            self.menu_open = False
        print(f"menu selecting {self.menuy}")


# Rendering
def render(epd, game):
    fb = epd.fb
    fb.fill(1)          # white background
    epd.gray_fb.fill(0) # gray

    draw_grid(fb)
    draw_numbers(fb, epd.gray_fb, game)
    draw_cursor(fb, game)
    draw_status(fb, game)
    draw_jots(fb,epd.gray_fb,game)

    epd.display_gray()

def cell_xy(row, col):
    """Return top-left pixel of cell (row, col)."""
    x = GRID_LEFT + col * CELL_SIZE
    y = GRID_TOP  + row * CELL_SIZE
    return x, y

def draw_grid(fb):
    total = 9 * CELL_SIZE
    # Thin cell lines
    for i in range(10):
        x = GRID_LEFT + i * CELL_SIZE
        y = GRID_TOP  + i * CELL_SIZE
        for t in range(CELL_THICK):
            fb.vline(x+t, GRID_TOP,  total, 0)
            fb.hline(GRID_LEFT, y+t, total, 0)
    # Thick box lines
    for b in range(4):
        x = GRID_LEFT + b * 3 * CELL_SIZE
        y = GRID_TOP  + b * 3 * CELL_SIZE
        for t in range(BOX_THICK):
            fb.vline(x+t, GRID_TOP,  total, 0)
            fb.hline(GRID_LEFT, y+t, total, 0)

def fill_cell_gray(gray_fb, r, c):
    # make a gray box
    x, y = cell_xy(r, c)
    for dy in range(1, CELL_SIZE - 1):
        gray_fb.hline(x + 1, y + dy, CELL_SIZE - 2, 1)

def fill_candidate_gray(gray_fb, n, r, c):
    sub = CELL_SIZE // 3
    x, y = cell_xy(r,c)
    idx = n - 1
    sub_row, sub_col = idx // 3, idx % 3

    px = x + sub_col * sub + (sub - 4 * JOT_SCALE ) // 2
    py = y + sub_row * sub + (sub - 6 * JOT_SCALE ) // 2
    
    for dy in range(1, (CELL_SIZE - 1)//3):
        gray_fb.hline(px, py + dy, (CELL_SIZE - 4)//3, 1)


def mark_cell_incorrect(fb, r, c):
    x, y = cell_xy(r, c)
    for dy in range(0, CELL_SIZE):
        fb.pixel(x + dy, y + dy,0)     
    print("cell incorrect")

def draw_numbers(fb, gray_fb, game):
    cr, cc = game.cursor_r, game.cursor_c
    selected_digit = game.board[cr][cc]
    for r in range(9):
        for c in range(9):
            val = game.board[r][c]
            if (selected_digit != 0
                    and val == selected_digit
                    ):
                fill_cell_gray(gray_fb, r, c)

            if val == 0:
                continue
            x, y = cell_xy(r, c)
            px = x + DIGIT_OFF_X
            py = y + DIGIT_OFF_Y
            clue = game.is_clue(r, c)
            if clue:
                # Clue digits bold
                draw_digit(fb, val, px,   py,   DIGIT_SCALE, 0)
                draw_digit(fb, val, px+1, py,   DIGIT_SCALE, 0)
            elif game.board[r][c] == game.solution[r][c]:
                # Player digits thinner 
                draw_digit(fb, val, px, py, DIGIT_SCALE, 0)
                print(f"drew {val}")
            else:
                draw_digit(fb, val, px, py, DIGIT_SCALE, 0)
                mark_cell_incorrect(fb, r, c)
                print(f"drew {val} but it is incorrect")

def draw_jots(fb, gray_fb, game):
    cr, cc = game.cursor_r, game.cursor_c
    selected_digit = game.board[cr][cc]
    
    sub = CELL_SIZE // 3
    for r in range(9):
        for c in range(9):
            if game.board[r][c] != 0:
                continue

            cell_candidates = game.candidates[r][c]
            if not cell_candidates:
                continue

            x, y = cell_xy(r, c)
            for n in cell_candidates:
                idx = n - 1
                sub_row, sub_col = idx // 3, idx % 3

                px = x + sub_col * sub + (sub - 4 * JOT_SCALE ) // 2
                py = y + sub_row * sub + (sub - 6 * JOT_SCALE ) // 2
                draw_digit(fb, n, px, py, JOT_SCALE, 0)

                if (selected_digit != 0
                    and n == selected_digit):
                    print(f"highlighting {n}")
                    fill_candidate_gray(gray_fb, n, r, c)



def draw_cursor(fb, game):
    if game.solved:
        return
    r, c = game.cursor_r, game.cursor_c
    x, y = cell_xy(r, c)
    # Draw a 2-pixel inset highlight rectangle
    margin = 3
    for t in range(2):
        fb.rect(x + margin + t, y + margin + t,
                CELL_SIZE - 2*margin - t,
                CELL_SIZE - 2*margin - t, 0)
    

def _draw_text5x7(fb, text, x, y, scale=1):
    """Draw a string using our digit font (only digits supported)."""
    cx = x
    for ch in text:
        if ch in FONT5x7:
            draw_digit(fb, int(ch), cx, y, scale, 0)
            cx += 5*scale + scale

def draw_status(fb, game):
    penciltxt = "Pencil: ON" if game.pencil else "Pencil: OFF"
    fb.text(f"Mistakes: {game.errors}", GRID_LEFT, STATUS_Y, 0)
    fb.text(f"{penciltxt}", GRID_LEFT + 100, STATUS_Y, 0)
    timer = str(timedelta(seconds=int(game.elapsed_time)))
    fb.text(f"{timer}",GRID_LEFT + 215, STATUS_Y, 0)

def draw_menu(epd, game):
    fb = epd.fb
    for dy in range(1, 125):
        fb.hline(130, 75 + dy, 140, 1)
    fb.hline(130, 75, 140, 0)
    fb.hline(130, 74, 140, 0)
    fb.hline(130, 200, 140, 0)
    fb.hline(130, 201, 140, 0)
    fb.vline(130,75,125,0)
    fb.vline(129,75,125,0)
    fb.vline(270,75,125,0)
    fb.vline(271,75,125,0)
    for dy in range(125):
        epd.gray_fb.hline(130, 75 + dy, 140, 0)
    fb.text("MENU", 160,90,0)
    fb.text("New Game", 160,110,0)
    fb.text("Restart", 160,130,0)
    fb.text("Close", 160,150,0)
    draw_menucursor(fb, game)
    epd.display()
    print("drew menu")
    
def draw_menucursor(fb, game):
    menuy = game.menuy
    #rectangle?
    for t in range(2):
        fb.rect(150, 110 + menuy * 18 - t,
                100,
                15, 0)


HOLD_MS = 2000   # hold SELECT this long for new game

# Main loop

def main():
    epd  = EPD()
    game = SudokuGame()

    press_times = {}  # key_char -> ticks_ms when pressed

    # Initial draw
    render(epd, game)
    dirty = False

    while True:
        game.elapsed_time = time.time() - game.start_time

        event = km.events.get()
        if event:
            key_char = KEY_MAP[event.key_number]
            now = time.ticks_ms()

            if event.pressed:
                press_times[key_char] = now
            else:  # released
                pressed_at = press_times.pop(key_char, None)
                duration = time.ticks_diff(now, pressed_at) if pressed_at is not None else 0
                ev = 'hold' if duration >= HOLD_MS else 'tap'

                if key_char == 'U':
                    if game.menu_open:
                        game.menumove(-1); dirty = True
                        print("menu up")
                    else:
                        game.move(-1, 0); dirty = True
                elif key_char == 'D':
                    if game.menu_open:
                        game.menumove(1); dirty = True
                        print("menu down")
                    else:
                        game.move(1, 0); dirty = True
                elif key_char == 'L':
                    game.move(0, -1); dirty = True
                elif key_char == 'R':
                    game.move(0, 1); dirty = True
                elif key_char == 'S':
                    if ev == 'hold':
                        game.new_game(); dirty = True
                    else:
                        if game.menu_open:
                            game.menuselect(); dirty = True
                        else:
                            print("select")
                elif key_char in '123456789':
                    num = int(key_char)
                    if game.pencil:
                        game.jot(num); dirty = True
                    else:
                        game.input(num); dirty = True
                    print(key_char)
                elif key_char == 'P':
                    if ev == 'hold':
                        print("power")
                elif key_char == 'M':
                    game.menu_open = not game.menu_open
                    if game.menu_open:
                        draw_menu(epd, game)
                    else:
                        dirty = True
                    print("menu")
                elif key_char == 'N':
                    game.undo(); dirty = True
                    print("undo")
                elif key_char == 'J':
                    game.pencil = not game.pencil
                    dirty = True
                    print(f"pencil {game.pencil}")

        if dirty:
            if game.menu_open:
                draw_menu(epd, game)
            else:
                render(epd, game)
            dirty = False

main()
