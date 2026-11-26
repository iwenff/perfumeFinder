from app.keyboards.main_menu import button, keyboard, menu_button


def volumes():
    return keyboard(
        [button(f"{value} мл", f"volume:{value}") for value in (2, 5, 10, 15)],
        [button(f"{value} мл", f"volume:{value}") for value in (30, 50, 100)],
        [button("Любой объём", "volume:any"), button("Ввести свой объём", "volume:custom")],
        [menu_button()],
    )


def volume_text(volume):
    return f"{volume:g} мл" if volume is not None else "Любой объём"


def cancel(run):
    return keyboard([button("❌ Отменить поиск", f"cancel:{run}")])
