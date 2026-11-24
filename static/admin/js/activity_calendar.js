const picker = document.querySelector("[data-period-picker]");
const form = picker.querySelector("[data-month-picker]");

form.addEventListener("change", () => form.requestSubmit());
form.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.name === "year") {
        event.preventDefault();
        form.requestSubmit();
    }
});
document.addEventListener("click", (event) => {
    if (!picker.contains(event.target)) picker.open = false;
});
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && picker.open) {
        picker.open = false;
        picker.querySelector("summary").focus();
    }
});
