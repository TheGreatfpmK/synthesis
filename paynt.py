import paynt.cli
import faulthandler

if __name__ == "__main__":
    faulthandler.enable()
    paynt.cli.main()