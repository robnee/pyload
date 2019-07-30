from tkinter import Tk, RIGHT, BOTH, RAISED
from tkinter.ttk import Frame, Button, Style


class Example(Frame):

    def __init__(self):
        super().__init__()

        self.initUI()

    def initUI(self):
        self.master.title("Simple")
        self.style = Style()
        # self.style.configure("TFrame", background="#333")
        print(self.style.theme_names())
        # self.style.theme_use("clam")

        frame = Frame(self, relief=RAISED, borderwidth=1)
        frame.pack(fill=BOTH, expand=True)

        self.pack(fill=BOTH, expand=1)

        self.centerWindow()

        progButton = Button(self, text="Program")
        progButton.pack(side=RIGHT)
        closeButton = Button(self, text="Close")
        closeButton.pack(side=RIGHT, padx=5, pady=5)
        okButton = Button(self, text="OK")
        okButton.pack(side=RIGHT)

    def centerWindow(self):
        w = 600
        h = 400

        sw = self.master.winfo_screenwidth()
        sh = self.master.winfo_screenheight()

        x = (sw - w) / 2
        y = (sh - h) / 2
        self.master.geometry('%dx%d+%d+%d' % (w, h, x, y))

def main():
    root = Tk()
    app = Example()
    root.mainloop()


if __name__ == '__main__':
    main()