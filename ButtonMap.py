import pygame

pygame.init()
pygame.joystick.init()

count = pygame.joystick.get_count()
print("Antall joysticks:", count)

if count == 0:
    print("Ingen joystick funnet.")
    raise SystemExit

js = pygame.joystick.Joystick(0)
js.init()

print("Navn:", js.get_name())
print("Antall akser:", js.get_numaxes())
print("Antall knapper:", js.get_numbuttons())

print("Beveg én bryter eller stikke om gangen. Ctrl+C for å stoppe.")

while True:
    pygame.event.pump()

    axes = [js.get_axis(i) for i in range(js.get_numaxes())]
    buttons = [js.get_button(i) for i in range(js.get_numbuttons())]

    print("Akser:", axes)
    print("Knapper:", buttons)
    print("-" * 40)