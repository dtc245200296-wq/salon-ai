(() => {
  const describeField = (field) => {
    const label = field.id
      ? field.form.querySelector(`label[for="${CSS.escape(field.id)}"]`)
      : null;
    const text = label?.textContent?.trim().replace(/\s+/g, " ");
    return text || field.getAttribute("aria-label") || field.name || "trường này";
  };

  const validationMessage = (field) => {
    const label = describeField(field);
    if (field.validity.valueMissing) {
      return field.type === "checkbox"
        ? `Vui lòng chọn ${label.toLowerCase()}.`
        : `Vui lòng nhập ${label.toLowerCase()}.`;
    }
    if (field.validity.typeMismatch && field.type === "email") {
      return "Vui lòng nhập địa chỉ email hợp lệ.";
    }
    if (field.type === "email" && /\/register\/?$/.test(field.form.action)
        && (!/^[A-Za-z0-9](?:[A-Za-z0-9._%+-]*[A-Za-z0-9])?@gmail\.com$/i.test(field.value.trim())
          || field.value.includes(".."))) {
      return "Email phải đúng định dạng @gmail.com.";
    }
    if (field.validity.rangeUnderflow && field.type === "date") {
      return "Ngày hẹn không được ở trong quá khứ.";
    }
    if (field.name === "username" && field.value.trim().length < 4) {
      return "Tên đăng nhập phải có ít nhất 4 ký tự.";
    }
    if (field.name === "phone" && field.value && !/^0\d{9}$/.test(field.value.trim())) {
      return "Số điện thoại phải gồm 10 chữ số và bắt đầu bằng 0.";
    }
    return "Vui lòng kiểm tra lại thông tin này.";
  };

  const clearError = (field) => {
    field.classList.remove("is-invalid");
    const feedbackId = field.dataset.feedbackId;
    if (feedbackId) document.getElementById(feedbackId)?.remove();
    delete field.dataset.feedbackId;
    field.removeAttribute("aria-describedby");
  };

  const showError = (field, message) => {
    clearError(field);
    field.classList.add("is-invalid");
    const feedback = document.createElement("div");
    feedback.className = "invalid-feedback d-block";
    feedback.id = `validation-${Math.random().toString(36).slice(2)}`;
    feedback.textContent = message;
    field.insertAdjacentElement("afterend", feedback);
    field.dataset.feedbackId = feedback.id;
    field.setAttribute("aria-describedby", feedback.id);
  };

  document.querySelectorAll("form[novalidate]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      let firstInvalid = null;
      form.querySelectorAll("input, select, textarea").forEach((field) => {
        if (field.disabled || field.type === "hidden" || field.type === "submit") return;
        const message = validationMessage(field);
        const registrationEmailInvalid = field.type === "email"
          && /\/register\/?$/.test(form.action)
          && (!/^[A-Za-z0-9](?:[A-Za-z0-9._%+-]*[A-Za-z0-9])?@gmail\.com$/i.test(field.value.trim())
            || field.value.includes(".."));
        if (field.required || (field.type === "email" && field.value.trim())
            || (field.name === "phone" && field.value.trim())
            || (field.name === "username" && field.value.trim())
            || registrationEmailInvalid) {
          if (!field.checkValidity() || (field.name === "username" && field.value.trim().length < 4)
              || (field.name === "phone" && field.value && !/^0\d{9}$/.test(field.value.trim()))
              || registrationEmailInvalid) {
            showError(field, message);
            firstInvalid ||= field;
            return;
          }
        }
        clearError(field);
      });

      if (form.id === "booking-form") {
        const serviceChecks = form.querySelectorAll('input[name="service_ids"]');
        const selected = Array.from(serviceChecks).some((input) => input.checked);
        const feedbackId = "booking-service-validation";
        document.getElementById(feedbackId)?.remove();
        serviceChecks.forEach((input) => input.classList.toggle("is-invalid", !selected));
        if (serviceChecks.length && !selected) {
          const feedback = document.createElement("div");
          feedback.id = feedbackId;
          feedback.className = "invalid-feedback d-block mt-2";
          feedback.textContent = "Vui lòng chọn ít nhất một dịch vụ.";
          form.querySelector(".booking-panel .row")?.insertAdjacentElement("afterend", feedback);
          firstInvalid ||= serviceChecks[0];
        }
      }

      if (firstInvalid) {
        event.preventDefault();
        firstInvalid.focus({ preventScroll: false });
      }
    });

    form.addEventListener("input", (event) => {
      if (event.target.matches("input, select, textarea")) clearError(event.target);
    });
    form.addEventListener("change", (event) => {
      if (event.target.matches("input, select, textarea")) clearError(event.target);
      if (form.id === "booking-form" && event.target.name === "service_ids" && event.target.checked) {
        document.getElementById("booking-service-validation")?.remove();
        form.querySelectorAll('input[name="service_ids"]').forEach((input) => input.classList.remove("is-invalid"));
      }
    });
  });
})();
