def get_number(prompt):
    while True:
        value = input(prompt)
        try:
            return float(value)
        except ValueError:
            print("Please enter a valid number.")


def calculate(first_number, operator, second_number):
    if operator == "+":
        return first_number + second_number
    if operator == "-":
        return first_number - second_number
    if operator == "*":
        return first_number * second_number
    if operator == "/":
        if second_number == 0:
            raise ZeroDivisionError("Cannot divide by zero.")
        return first_number / second_number

    raise ValueError("Unknown operator.")


def main():
    print("Simple Calculator")
    print("Available operations: +, -, *, /")

    while True:
        first_number = get_number("First number: ")
        operator = input("Operation: ").strip()
        second_number = get_number("Second number: ")

        try:
            result = calculate(first_number, operator, second_number)
        except (ValueError, ZeroDivisionError) as error:
            print(error)
        else:
            print(f"Result: {result}")

        again = input("Calculate again? (y/n): ").strip().lower()
        if again != "y":
            print("Goodbye.")
            break


if __name__ == "__main__":
    main()
