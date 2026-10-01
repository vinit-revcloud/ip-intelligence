
document.querySelectorAll("nav button").forEach(btn=>{
 btn.onclick=()=>{
   document.querySelectorAll(".page").forEach(p=>p.classList.add("hidden"));
   document.getElementById(btn.dataset.page).classList.remove("hidden");
   document.getElementById("title").innerText=btn.innerText;
 }
});
