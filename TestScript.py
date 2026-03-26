import pygame

pygame.init()
pygame.joystick.init()

js = pygame.joystick.Joystick(0)
js.init()

print("Move one stick at a time...")

while True:
    pygame.event.pump()
    axes = [round(js.get_axis(i), 2) for i in range(js.get_numaxes())]
    print(axes)